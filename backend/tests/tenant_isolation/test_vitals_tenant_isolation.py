"""Tenant-isolation suite for the Vitals module — PRD-ARCHITECTURE.md §27.
Same approach as every other module's suite: prove isolation through the
real HTTP API and through a deliberately unscoped direct query (the RLS
backstop) — plus a check that `vitals` is append-only at the DB level
(PRD §5.3), same as `audit_logs` (migration 0007).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.checkin.models import Encounter
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic
from app.modules.vitals.models import Vitals

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"vitals-isolation-{uuid.uuid4().hex[:10]}"
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


async def _seed_encounter(clinic: Clinic, branch_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Directly creates a Patient + Encounter (bypassing the HTTP API) so
    isolation/append-only tests can insert a Vitals row without depending
    on the Check-in module's own endpoints. Returns (patient_id, encounter_id)."""
    async with tenant_session(clinic.id) as session:
        patient = Patient(tenant_id=clinic.id, mrn=f"MRN-VITALS-{uuid.uuid4().hex[:8]}", first_name="P")
        session.add(patient)
        await session.flush()
        encounter = Encounter(tenant_id=clinic.id, branch_id=uuid.UUID(branch_id), appointment_id=None, patient_id=patient.id)
        session.add(encounter)
        await session.flush()
        return patient.id, encounter.id


async def test_vitals_created_in_one_tenant_are_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@vitals-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@vitals-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@vitals-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@vitals-b.clinic", "pw")

        branch_id = await _create_branch(api_client, headers_a)
        _, encounter_id = await _seed_encounter(clinic_a, branch_id)

        created = await api_client.post(
            "/api/v1/vitals", json={"encounter_id": str(encounter_id), "heart_rate": 72}, headers=headers_a
        )
        assert created.status_code == 201
        vitals_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/vitals", headers=headers_b)
        assert all(v["id"] != vitals_id for v in list_b.json()["items"])

        direct_b = await api_client.get(f"/api/v1/vitals/{vitals_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/vitals/{vitals_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_vitals_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@vitals-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@vitals-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@vitals-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@vitals-d.clinic", "pw")
        branch_a_id = await _create_branch(api_client, headers_a)
        branch_b_id = await _create_branch(api_client, headers_b)

        patient_a_id, encounter_a_id = await _seed_encounter(clinic_a, branch_a_id)
        patient_b_id, encounter_b_id = await _seed_encounter(clinic_b, branch_b_id)

        async with tenant_session(clinic_a.id) as session:
            reading_a = Vitals(
                tenant_id=clinic_a.id, encounter_id=encounter_a_id, patient_id=patient_a_id, recorded_by=owner_a_id, recorded_by_role="OWNER", heart_rate=70
            )
            session.add(reading_a)
            await session.flush()
            reading_a_id = reading_a.id

        async with tenant_session(clinic_b.id) as session:
            session.add(
                Vitals(
                    tenant_id=clinic_b.id, encounter_id=encounter_b_id, patient_id=patient_b_id, recorded_by=owner_b_id, recorded_by_role="OWNER", heart_rate=71
                )
            )

        async with tenant_session(clinic_a.id) as session:
            # No `.where(Vitals.tenant_id == ...)` — the app-layer mistake
            # RLS exists to catch.
            result = await session.execute(select(Vitals))
            visible_ids = {v.id for v in result.scalars().all()}

        assert visible_ids == {reading_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_vitals_is_append_only_at_the_db_level(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    """PRD §5.3: vitals is insert-only — a new reading is always a new
    row, never an update to the previous one. Enforced by
    prevent_update_delete() (migration 0012) plus app_user having no
    UPDATE/DELETE grant on the table, not just app convention."""
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@vitals-e.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@vitals-e.clinic", "pw")
        branch_id = await _create_branch(api_client, headers_a)
        patient_id, encounter_id = await _seed_encounter(clinic_a, branch_id)

        async with tenant_session(clinic_a.id) as session:
            reading = Vitals(
                tenant_id=clinic_a.id, encounter_id=encounter_id, patient_id=patient_id, recorded_by=owner_a_id, recorded_by_role="OWNER", heart_rate=70
            )
            session.add(reading)
            await session.flush()
            reading_id = reading.id

        with pytest.raises(Exception):
            async with tenant_session(clinic_a.id) as session:
                await session.execute(text("UPDATE vitals SET heart_rate = 999 WHERE id = :id"), {"id": str(reading_id)})

        with pytest.raises(Exception):
            async with tenant_session(clinic_a.id) as session:
                await session.execute(text("DELETE FROM vitals WHERE id = :id"), {"id": str(reading_id)})
    finally:
        await _teardown([clinic_a.id])
