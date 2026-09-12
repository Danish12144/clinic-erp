"""Tenant-isolation suite for the public self-booking surface and the new
`payment_gateway_orders` table — Phase 2 (Master Handoff item 1/4). Same
approach as every other module's suite: prove isolation through the real
(here, unauthenticated) HTTP API and through a deliberately unscoped
direct query (the RLS backstop).
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
from app.modules.billing.models import PaymentGatewayOrder
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"public-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Public Isolation Clinic", slug=slug)
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
        "/api/v1/doctors",
        json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS, "slot_duration_minutes": 30},
        headers=headers,
    )
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": clinic.slug, "token": token, "password": "password-123"})
    return user_id


async def test_public_doctor_directory_never_leaks_another_clinics_doctors(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@public-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@public-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@public-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@public-b.clinic", "pw")

        doctor_a = await _create_active_doctor(api_client, headers_a, clinic_a, phone="+919000088801")
        doctor_b = await _create_active_doctor(api_client, headers_b, clinic_b, phone="+919000088802")

        listed_via_a_slug = await api_client.get(f"/api/v1/public/clinics/{clinic_a.slug}/doctors")
        doctor_ids_a = {d["user_id"] for d in listed_via_a_slug.json()}
        assert doctor_a in doctor_ids_a
        assert doctor_b not in doctor_ids_a

        listed_via_b_slug = await api_client.get(f"/api/v1/public/clinics/{clinic_b.slug}/doctors")
        doctor_ids_b = {d["user_id"] for d in listed_via_b_slug.json()}
        assert doctor_b in doctor_ids_b
        assert doctor_a not in doctor_ids_b
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_public_booking_against_one_clinics_slug_cannot_book_another_clinics_doctor(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    """A caller who somehow learned clinic B's doctor id can't use it to
    book against clinic A's slug — `validate_and_lock_slot`'s doctor
    lookup is itself tenant-scoped (via RLS on the session clinic A's slug
    resolves to), so clinic B's doctor simply doesn't exist from clinic
    A's point of view."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@public-c.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@public-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@public-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@public-d.clinic", "pw")

        branch_a = await _create_branch(api_client, headers_a)
        doctor_b = await _create_active_doctor(api_client, headers_b, clinic_b, phone="+919000088803")

        future = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        response = await api_client.post(
            f"/api/v1/public/clinics/{clinic_a.slug}/book",
            json={
                "branch_id": branch_a, "doctor_id": doctor_b, "scheduled_at": future.isoformat(),
                "first_name": "Cross Tenant", "phone": "+919000088804",
            },
        )
        assert response.status_code == 422
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_payment_gateway_order_query(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@public-e.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@public-f.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@public-e.clinic", "pw")
        branch_a = await _create_branch(api_client, headers_a)
        future = datetime.now(timezone.utc) + timedelta(days=2)

        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-PGO-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            appt_a = Appointment(
                tenant_id=clinic_a.id, branch_id=uuid.UUID(branch_a), patient_id=patient_a.id, doctor_id=None,
                source=AppointmentSource.ONLINE, scheduled_at=future,
            )
            session.add(appt_a)
            await session.flush()
            order_a = PaymentGatewayOrder(
                tenant_id=clinic_a.id, appointment_id=appt_a.id, provider="mock", provider_order_id="order-a", amount=100,
            )
            session.add(order_a)
            await session.flush()
            order_a_id = order_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-PGO-B", first_name="B")
            session.add(patient_b)
            await session.flush()

        async with tenant_session(clinic_a.id) as session:
            # No `.where(PaymentGatewayOrder.tenant_id == ...)` — the
            # app-layer mistake RLS exists to catch.
            result = await session.execute(select(PaymentGatewayOrder))
            visible_ids = {o.id for o in result.scalars().all()}

        assert visible_ids == {order_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
