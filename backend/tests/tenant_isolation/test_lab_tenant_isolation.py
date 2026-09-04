"""Tenant-isolation suite for Pathology / Diagnostic Lab Management —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop) across all three new tables.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.lab.models import LabOrder, LabResult, LabTestCatalogItem
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"lab-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()
        user = User(tenant_id=clinic.id, role_id=role_map["OWNER"], email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug), user.id


async def _login(api_client: AsyncClient, clinic: Clinic, email: str, password: str) -> dict[str, str]:
    response = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": clinic.slug, "identifier": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def _enable_lab_feature(api_client: AsyncClient, headers: dict[str, str]) -> None:
    response = await api_client.put("/api/v1/clinics/me/settings/features.lab_enabled", json={"value": True}, headers=headers)
    assert response.status_code == 200


async def _create_branch(api_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "Branch"}, headers=headers)
    return response.json()["id"]


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_lab_order_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@lab-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@lab-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@lab-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@lab-b.clinic", "pw")
        await _enable_lab_feature(api_client, headers_a)
        await _enable_lab_feature(api_client, headers_b)

        branch_a = await _create_branch(api_client, headers_a)
        patient_a = await _create_patient(api_client, headers_a, phone="+919000599901")
        walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_a, "branch_id": branch_a}, headers=headers_a)
        encounter_a = walk_in.json()["encounter"]["id"]
        test_created = await api_client.post("/api/v1/lab/tests", json={"name": "IsolationTest"}, headers=headers_a)
        test_a = test_created.json()["id"]
        order_created = await api_client.post("/api/v1/lab/orders", json={"encounter_id": encounter_a, "test_id": test_a}, headers=headers_a)
        order_a = order_created.json()["id"]

        list_b = await api_client.get("/api/v1/lab/orders", headers=headers_b)
        assert all(o["id"] != order_a for o in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/lab/orders/{order_a}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/lab/orders/{order_a}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_lab_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@lab-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@lab-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            from app.modules.checkin.models import Encounter as EncounterModel
            from app.modules.tenancy.models import Branch

            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-LAB-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            test_a = LabTestCatalogItem(tenant_id=clinic_a.id, name="A")
            session.add(test_a)
            await session.flush()
            branch_a = Branch(tenant_id=clinic_a.id, name="Branch A")
            session.add(branch_a)
            await session.flush()
            encounter_a = EncounterModel(tenant_id=clinic_a.id, branch_id=branch_a.id, appointment_id=None, patient_id=patient_a.id)
            session.add(encounter_a)
            await session.flush()
            order_a = LabOrder(tenant_id=clinic_a.id, encounter_id=encounter_a.id, patient_id=patient_a.id, test_id=test_a.id, ordered_by=owner_a_id)
            session.add(order_a)
            await session.flush()
            result_a = LabResult(tenant_id=clinic_a.id, lab_order_id=order_a.id, parameter="p", value="1", entered_by=owner_a_id)
            session.add(result_a)
            await session.flush()
            test_a_id, order_a_id, result_a_id = test_a.id, order_a.id, result_a.id

        async with tenant_session(clinic_b.id) as session:
            from app.modules.checkin.models import Encounter as EncounterModelB
            from app.modules.tenancy.models import Branch as BranchB

            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-LAB-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            test_b = LabTestCatalogItem(tenant_id=clinic_b.id, name="B")
            session.add(test_b)
            await session.flush()
            branch_b = BranchB(tenant_id=clinic_b.id, name="Branch B")
            session.add(branch_b)
            await session.flush()
            encounter_b = EncounterModelB(tenant_id=clinic_b.id, branch_id=branch_b.id, appointment_id=None, patient_id=patient_b.id)
            session.add(encounter_b)
            await session.flush()
            order_b = LabOrder(tenant_id=clinic_b.id, encounter_id=encounter_b.id, patient_id=patient_b.id, test_id=test_b.id, ordered_by=owner_b_id)
            session.add(order_b)
            await session.flush()
            session.add(LabResult(tenant_id=clinic_b.id, lab_order_id=order_b.id, parameter="p", value="1", entered_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            test_result = await session.execute(select(LabTestCatalogItem))
            visible_test_ids = {t.id for t in test_result.scalars().all()}
            order_result = await session.execute(select(LabOrder))
            visible_order_ids = {o.id for o in order_result.scalars().all()}
            result_result = await session.execute(select(LabResult))
            visible_result_ids = {r.id for r in result_result.scalars().all()}

        assert visible_test_ids == {test_a_id}
        assert visible_order_ids == {order_a_id}
        assert visible_result_ids == {result_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
