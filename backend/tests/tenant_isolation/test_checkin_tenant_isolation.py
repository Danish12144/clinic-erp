"""Tenant-isolation suite for the Check-in module (encounters + queue
tokens) — PRD-ARCHITECTURE.md §27. Same approach as every other module's
suite: prove isolation through the real HTTP API and through a
deliberately unscoped direct query (the RLS backstop).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.checkin.models import Encounter, QueueToken
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"checkin-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()

        user = User(tenant_id=clinic.id, role_id=role_map["OWNER"], email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()

        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug), user.id


async def _login(api_client: AsyncClient, clinic: Clinic, email: str, password: str) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/staff/login", json={"clinic_slug": clinic.slug, "identifier": email, "password": password}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def _create_branch(api_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "Branch"}, headers=headers)
    return response.json()["id"]


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_encounter_and_token_created_in_one_tenant_are_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@checkin-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@checkin-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@checkin-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@checkin-b.clinic", "pw")

        branch_id = await _create_branch(api_client, headers_a)
        patient_id = await _create_patient(api_client, headers_a, phone="+919000199901")

        walk_in = await api_client.post(
            "/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=headers_a
        )
        encounter_id = walk_in.json()["encounter"]["id"]
        token_id = walk_in.json()["queue_token"]["id"]

        list_b = await api_client.get("/api/v1/encounters", headers=headers_b)
        assert all(e["id"] != encounter_id for e in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/encounters/{encounter_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/encounters/{encounter_id}", headers=headers_a)
        assert direct_a.status_code == 200

        queue_b = await api_client.get("/api/v1/queue", headers=headers_b)
        assert all(t["id"] != token_id for t in queue_b.json()["items"])
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_encounter_and_queue_token_query(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@checkin-c.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@checkin-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@checkin-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@checkin-d.clinic", "pw")
        branch_a_id = await _create_branch(api_client, headers_a)
        branch_b_id = await _create_branch(api_client, headers_b)

        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-CHECKIN-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            encounter_a = Encounter(tenant_id=clinic_a.id, branch_id=uuid.UUID(branch_a_id), appointment_id=None, patient_id=patient_a.id)
            session.add(encounter_a)
            await session.flush()
            token_a = QueueToken(
                tenant_id=clinic_a.id, branch_id=uuid.UUID(branch_a_id), encounter_id=encounter_a.id, doctor_id=None, token_number=1
            )
            session.add(token_a)
            await session.flush()
            encounter_a_id = encounter_a.id
            token_a_id = token_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-CHECKIN-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            encounter_b = Encounter(tenant_id=clinic_b.id, branch_id=uuid.UUID(branch_b_id), appointment_id=None, patient_id=patient_b.id)
            session.add(encounter_b)
            await session.flush()
            session.add(
                QueueToken(tenant_id=clinic_b.id, branch_id=uuid.UUID(branch_b_id), encounter_id=encounter_b.id, doctor_id=None, token_number=1)
            )

        async with tenant_session(clinic_a.id) as session:
            # No `.where(Encounter.tenant_id == ...)` / `.where(QueueToken.tenant_id == ...)`
            # — the app-layer mistake RLS exists to catch.
            encounter_result = await session.execute(select(Encounter))
            visible_encounter_ids = {e.id for e in encounter_result.scalars().all()}
            token_result = await session.execute(select(QueueToken))
            visible_token_ids = {t.id for t in token_result.scalars().all()}

        assert visible_encounter_ids == {encounter_a_id}
        assert visible_token_ids == {token_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
