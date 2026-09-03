"""Tenant-isolation suite for the Patient Management module —
PRD-ARCHITECTURE.md §27. Same approach as the Auth and Tenancy modules'
suites: prove isolation through the real HTTP API and through a
deliberately unscoped direct query (the RLS backstop).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"patients-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_patient_created_in_one_tenant_is_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@patients-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@patients-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@patients-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@patients-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/patients", json={"first_name": "TenantA", "phone": "+919000011111"}, headers=headers_a
        )
        patient_id = created.json()["patient"]["id"]

        list_b = await api_client.get("/api/v1/patients", headers=headers_b)
        assert all(p["id"] != patient_id for p in list_b.json()["items"])

        search_by_phone_b = await api_client.get("/api/v1/patients?phone=%2B919000011111", headers=headers_b)
        assert search_by_phone_b.json()["total"] == 0

        direct_b = await api_client.get(f"/api/v1/patients/{patient_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/patients/{patient_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_duplicate_detection_never_crosses_tenants(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    """A patient in tenant A sharing a phone number with a patient in
    tenant B must never surface as a "possible duplicate" — that would be
    a cross-tenant data leak disguised as a helpful warning."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@patients-c.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@patients-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@patients-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@patients-d.clinic", "pw")

        shared_phone = "+919000022222"
        await api_client.post("/api/v1/patients", json={"first_name": "InTenantA", "phone": shared_phone}, headers=headers_a)

        created_b = await api_client.post(
            "/api/v1/patients", json={"first_name": "InTenantB", "phone": shared_phone}, headers=headers_b
        )
        assert created_b.json()["possible_duplicates"] == []
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_patient_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@patients-e.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@patients-f.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-A-0001", first_name="A")
            session.add(patient_a)
            await session.flush()
            patient_a_id = patient_a.id

        async with tenant_session(clinic_b.id) as session:
            session.add(Patient(tenant_id=clinic_b.id, mrn="MRN-B-0001", first_name="B"))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(Patient.tenant_id == ...)` — the app-layer mistake
            # RLS exists to catch.
            result = await session.execute(select(Patient))
            visible_ids = {p.id for p in result.scalars().all()}

        assert visible_ids == {patient_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_mrn_uniqueness_is_per_tenant_not_global(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    """The same MRN string in two different tenants must both succeed —
    the UNIQUE constraint is (tenant_id, mrn), not a global unique on mrn
    alone."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@patients-g.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@patients-h.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@patients-g.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@patients-h.clinic", "pw")

        response_a = await api_client.post(
            "/api/v1/patients", json={"first_name": "A", "phone": "+919000033331", "mrn": "MRN-SHARED-001"}, headers=headers_a
        )
        response_b = await api_client.post(
            "/api/v1/patients", json={"first_name": "B", "phone": "+919000033332", "mrn": "MRN-SHARED-001"}, headers=headers_b
        )

        assert response_a.status_code == 201
        assert response_b.status_code == 201
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
