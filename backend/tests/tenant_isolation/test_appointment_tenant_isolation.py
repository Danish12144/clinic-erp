"""Tenant-isolation suite for the Appointments module —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.appointments.models import Appointment, AppointmentSource
from app.modules.auth.models import User
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"appt-isolation-{uuid.uuid4().hex[:10]}"
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


async def _create_active_doctor(api_client: AsyncClient, headers: dict[str, str], clinic: Clinic, *, phone: str) -> str:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=headers
    )
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": clinic.slug, "token": token, "password": "password-123"})
    return user_id


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_appointment_created_in_one_tenant_is_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@appt-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@appt-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@appt-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@appt-b.clinic", "pw")

        branch_id = await _create_branch(api_client, headers_a)
        doctor_id = await _create_active_doctor(api_client, headers_a, clinic_a, phone="+919000099901")
        patient_id = await _create_patient(api_client, headers_a, phone="+919000099902")

        future = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        created = await api_client.post(
            "/api/v1/appointments",
            json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": future.isoformat()},
            headers=headers_a,
        )
        appointment_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/appointments", headers=headers_b)
        assert all(a["id"] != appointment_id for a in list_b.json()["items"])

        direct_b = await api_client.get(f"/api/v1/appointments/{appointment_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/appointments/{appointment_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_appointment_query(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@appt-c.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@appt-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@appt-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@appt-d.clinic", "pw")
        branch_a_id = await _create_branch(api_client, headers_a)
        branch_b_id = await _create_branch(api_client, headers_b)

        future = datetime.now(timezone.utc) + timedelta(days=2)

        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-APPT-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            appt_a = Appointment(
                tenant_id=clinic_a.id,
                branch_id=uuid.UUID(branch_a_id),
                patient_id=patient_a.id,
                doctor_id=None,
                source=AppointmentSource.WALK_IN,
                scheduled_at=future,
            )
            session.add(appt_a)
            await session.flush()
            appt_a_id = appt_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-APPT-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            session.add(
                Appointment(
                    tenant_id=clinic_b.id,
                    branch_id=uuid.UUID(branch_b_id),
                    patient_id=patient_b.id,
                    doctor_id=None,
                    source=AppointmentSource.WALK_IN,
                    scheduled_at=future,
                )
            )

        async with tenant_session(clinic_a.id) as session:
            # No `.where(Appointment.tenant_id == ...)` — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(Appointment))
            visible_ids = {a.id for a in result.scalars().all()}

        assert visible_ids == {appt_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
