"""Tenant-isolation suite for Consultation/Prescription — PRD-ARCHITECTURE.md
§27. Same approach as every other module's suite: prove isolation through
the real HTTP API and through a deliberately unscoped direct query (the RLS
backstop) — plus a check that `prescriptions` is append-only at the DB
level (PRD §5.4/§5.7), same as `vitals`/`audit_logs`.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.checkin.models import Encounter
from app.modules.consultation.models import Consultation, Prescription
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"consult-isolation-{uuid.uuid4().hex[:10]}"
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


async def _create_branch(api_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "Branch"}, headers=headers)
    return response.json()["id"]


async def _seed_encounter(clinic: Clinic, branch_id: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with tenant_session(clinic.id) as session:
        patient = Patient(tenant_id=clinic.id, mrn=f"MRN-CONSULT-{uuid.uuid4().hex[:8]}", first_name="P")
        session.add(patient)
        await session.flush()
        encounter = Encounter(tenant_id=clinic.id, branch_id=uuid.UUID(branch_id), appointment_id=None, patient_id=patient.id)
        session.add(encounter)
        await session.flush()
        return patient.id, encounter.id


async def test_consultation_and_prescription_created_in_one_tenant_are_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@consult-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@consult-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@consult-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@consult-b.clinic", "pw")

        branch_id = await _create_branch(api_client, headers_a)
        _, encounter_id = await _seed_encounter(clinic_a, branch_id)

        consultation = await api_client.post("/api/v1/consultations", json={"encounter_id": str(encounter_id)}, headers=headers_a)
        assert consultation.status_code == 201
        consultation_id = consultation.json()["id"]
        prescription = await api_client.post(
            "/api/v1/prescriptions", json={"encounter_id": str(encounter_id), "items": [{"medicine_name_freetext": "X", "prescribed_quantity": 1}]}, headers=headers_a
        )
        assert prescription.status_code == 201
        prescription_id = prescription.json()["id"]

        list_consultations_b = await api_client.get("/api/v1/consultations", headers=headers_b)
        assert all(c["id"] != consultation_id for c in list_consultations_b.json()["items"])
        direct_consultation_b = await api_client.get(f"/api/v1/consultations/{consultation_id}", headers=headers_b)
        assert direct_consultation_b.status_code == 404

        list_prescriptions_b = await api_client.get("/api/v1/prescriptions", headers=headers_b)
        assert all(p["id"] != prescription_id for p in list_prescriptions_b.json()["items"])
        direct_prescription_b = await api_client.get(f"/api/v1/prescriptions/{prescription_id}", headers=headers_b)
        assert direct_prescription_b.status_code == 404
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_consultation_and_prescription_query(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@consult-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@consult-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@consult-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@consult-d.clinic", "pw")
        branch_a_id = await _create_branch(api_client, headers_a)
        branch_b_id = await _create_branch(api_client, headers_b)

        _, encounter_a_id = await _seed_encounter(clinic_a, branch_a_id)
        _, encounter_b_id = await _seed_encounter(clinic_b, branch_b_id)

        async with tenant_session(clinic_a.id) as session:
            consultation_a = Consultation(tenant_id=clinic_a.id, encounter_id=encounter_a_id, doctor_id=owner_a_id)
            session.add(consultation_a)
            await session.flush()
            prescription_a = Prescription(tenant_id=clinic_a.id, encounter_id=encounter_a_id, doctor_id=owner_a_id)
            session.add(prescription_a)
            await session.flush()
            consultation_a_id = consultation_a.id
            prescription_a_id = prescription_a.id

        async with tenant_session(clinic_b.id) as session:
            session.add(Consultation(tenant_id=clinic_b.id, encounter_id=encounter_b_id, doctor_id=owner_b_id))
            session.add(Prescription(tenant_id=clinic_b.id, encounter_id=encounter_b_id, doctor_id=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            consultation_result = await session.execute(select(Consultation))
            visible_consultation_ids = {c.id for c in consultation_result.scalars().all()}
            prescription_result = await session.execute(select(Prescription))
            visible_prescription_ids = {p.id for p in prescription_result.scalars().all()}

        assert visible_consultation_ids == {consultation_a_id}
        assert visible_prescription_ids == {prescription_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_prescriptions_is_append_only_at_the_db_level(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    """PRD §5.4/§5.7: a prescription correction is a new row referencing
    the original via supersedes_prescription_id, never an edit — enforced
    by prevent_update_delete() (migration 0013), same mechanism as
    vitals/audit_logs."""
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@consult-e.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@consult-e.clinic", "pw")
        branch_id = await _create_branch(api_client, headers_a)
        _, encounter_id = await _seed_encounter(clinic_a, branch_id)

        async with tenant_session(clinic_a.id) as session:
            prescription = Prescription(tenant_id=clinic_a.id, encounter_id=encounter_id, doctor_id=owner_a_id)
            session.add(prescription)
            await session.flush()
            prescription_id = prescription.id

        with pytest.raises(Exception):
            async with tenant_session(clinic_a.id) as session:
                await session.execute(text("UPDATE prescriptions SET doctor_id = :id WHERE id = :pid"), {"id": str(owner_a_id), "pid": str(prescription_id)})

        with pytest.raises(Exception):
            async with tenant_session(clinic_a.id) as session:
                await session.execute(text("DELETE FROM prescriptions WHERE id = :id"), {"id": str(prescription_id)})
    finally:
        await _teardown([clinic_a.id])
