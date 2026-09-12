"""End-to-end tests of the public (unauthenticated) clinic discovery +
self-booking surface — Phase 2 (Master Handoff item 1) — against a real
Postgres. See tests/conftest.py (skipped automatically if unreachable).
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str) -> str:
    created = await api_client.post(
        "/api/v1/doctors",
        json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS, "slot_duration_minutes": 30},
        headers=owner_headers,
    )
    assert created.status_code == 201
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    accept = await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )
    assert accept.status_code == 200
    return user_id


def _future_slot(days: int = 1, hour: int = 10) -> datetime:
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=hour, minute=0, second=0, microsecond=0)


async def test_public_clinic_discovery(api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PublicBranch")
    await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000001")

    clinic_response = await api_client.get(f"/api/v1/public/clinics/{test_clinic.slug}")
    assert clinic_response.status_code == 200
    assert clinic_response.json()["slug"] == test_clinic.slug

    branches_response = await api_client.get(f"/api/v1/public/clinics/{test_clinic.slug}/branches")
    assert branches_response.status_code == 200
    assert any(b["id"] == branch_id for b in branches_response.json())

    doctors_response = await api_client.get(f"/api/v1/public/clinics/{test_clinic.slug}/doctors")
    assert doctors_response.status_code == 200
    assert len(doctors_response.json()) >= 1
    assert doctors_response.json()[0]["slot_duration_minutes"] == 30


async def test_unknown_clinic_slug_is_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/public/clinics/no-such-clinic-slug")
    assert response.status_code == 404


async def test_public_slots_reflect_working_hours_and_existing_bookings(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "SlotsBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000002")
    target_date = (datetime.now(timezone.utc) + timedelta(days=2)).date()

    before = await api_client.get(
        f"/api/v1/public/clinics/{test_clinic.slug}/doctors/{doctor_id}/slots", params={"on": target_date.isoformat()}
    )
    assert before.status_code == 200
    slots_before = before.json()["slots"]
    assert len(slots_before) > 0

    scheduled_at = slots_before[0]["scheduled_at"]
    booking = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": scheduled_at,
            "first_name": "Guest", "phone": "+919000000099",
        },
    )
    assert booking.status_code == 201, booking.text

    after = await api_client.get(
        f"/api/v1/public/clinics/{test_clinic.slug}/doctors/{doctor_id}/slots", params={"on": target_date.isoformat()}
    )
    slots_after = [s["scheduled_at"] for s in after.json()["slots"]]
    assert scheduled_at not in slots_after


async def test_public_booking_creates_a_new_patient_and_free_appointment(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "BookBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000003")
    scheduled_at = _future_slot(days=3, hour=11)

    response = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": scheduled_at.isoformat(),
            "first_name": "Brand New", "last_name": "Patient", "phone": "+919000000004",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "SCHEDULED"
    assert body["payment_status"] == "NOT_REQUIRED"
    assert body["gateway_order"] is None

    # A second booking with the same phone reuses the same patient, not a duplicate.
    second_scheduled_at = _future_slot(days=3, hour=12)
    second = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": second_scheduled_at.isoformat(),
            "first_name": "Brand New", "phone": "+919000000004",
        },
    )
    assert second.status_code == 201
    assert second.json()["patient_id"] == body["patient_id"]


async def test_public_booking_requires_prepayment_amount_when_requested(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PrepayBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000005")

    response = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=4).isoformat(),
            "first_name": "Needs Payment", "phone": "+919000000006", "request_prepayment": True,
        },
    )
    assert response.status_code == 422


async def test_public_booking_with_mock_gateway_creates_pending_order(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PrepayBranch2")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000007")

    response = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=5).isoformat(),
            "first_name": "Prepay", "phone": "+919000000008", "request_prepayment": True, "prepayment_amount": "100.00",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["payment_status"] == "PENDING"
    assert body["gateway_order"]["provider"] == "mock"
    assert body["gateway_order"]["order_id"].startswith("mock_order_")


async def test_retry_payment_requires_matching_phone(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "RetryBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000009")

    booking = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=6).isoformat(),
            "first_name": "Retry Me", "phone": "+919000000010", "request_prepayment": True, "prepayment_amount": "50.00",
        },
    )
    appointment_id = booking.json()["appointment_id"]

    wrong_phone = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/appointments/{appointment_id}/retry-payment",
        json={"phone": "+919999999999"},
    )
    assert wrong_phone.status_code == 404

    right_phone = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/appointments/{appointment_id}/retry-payment",
        json={"phone": "+919000000010"},
    )
    assert right_phone.status_code == 200
    assert right_phone.json()["order_id"].startswith("mock_order_")


async def test_concurrent_public_bookings_for_the_same_slot_only_one_succeeds(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    """Phase 2 (Master Handoff item 1, "prevent double-booking on
    concurrent requests") — fires two simultaneous booking requests for
    the exact same doctor+slot and asserts exactly one succeeds, thanks to
    AppointmentRepository.lock_doctor_for_booking's advisory lock."""
    branch_id = await _create_branch(api_client, owner_headers, "RaceBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000011")
    scheduled_at = _future_slot(days=7).isoformat()

    async def _book(phone: str):
        return await api_client.post(
            f"/api/v1/public/clinics/{test_clinic.slug}/book",
            json={
                "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": scheduled_at,
                "first_name": "Racer", "phone": phone,
            },
        )

    results = await asyncio.gather(_book("+919000000012"), _book("+919000000013"))
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409], statuses


async def test_cancelling_a_confirmed_prepaid_booking_triggers_a_refund(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    """Phase 2 (Master Handoff items 4/5) — a CONFIRMED prepayment (set by
    the gateway webhook) triggers a real (mock-adapter) refund on
    cancellation, and payment_status moves to REFUNDED. This is
    AppointmentService._cancel's own refund branch, exercised through the
    ordinary staff cancel endpoint — cancellation doesn't need its own
    special "refund" route."""
    branch_id = await _create_branch(api_client, owner_headers, "RefundBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919000000014")

    booking = await api_client.post(
        f"/api/v1/public/clinics/{test_clinic.slug}/book",
        json={
            "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=8).isoformat(),
            "first_name": "Refund Me", "phone": "+919000000015", "request_prepayment": True, "prepayment_amount": "75.00",
        },
    )
    assert booking.status_code == 201
    appointment_id = booking.json()["appointment_id"]
    order_id = booking.json()["gateway_order"]["order_id"]

    # Simulate the gateway confirming this specific mock order via the
    # webhook path's DB-level effect directly (no real Razorpay webhook
    # exists for the "mock" provider) — same end state a real
    # payment.captured webhook would leave behind.
    from app.core.db import platform_admin_session
    from app.modules.appointments.models import AppointmentPaymentStatus
    from app.modules.appointments.repository import AppointmentRepository
    from app.modules.billing.models import PaymentGatewayOrderStatus
    from app.modules.billing.repository import PaymentGatewayOrderRepository

    async with platform_admin_session() as session:
        order_repo = PaymentGatewayOrderRepository(session)
        order = await order_repo.get_by_provider_order_id(provider="mock", provider_order_id=order_id)
        assert order is not None
        await order_repo.mark_status(order.id, status=PaymentGatewayOrderStatus.PAID, provider_payment_id="mock_pay_123")
        await AppointmentRepository(session).set_payment_status(order.appointment_id, payment_status=AppointmentPaymentStatus.CONFIRMED)

    cancelled = await api_client.post(
        f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "Patient changed plans"}, headers=owner_headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["payment_status"] == "REFUNDED"

    async with platform_admin_session() as session:
        refreshed_order = await PaymentGatewayOrderRepository(session).get_by_provider_order_id(provider="mock", provider_order_id=order_id)
        assert refreshed_order is not None
        assert refreshed_order.status == PaymentGatewayOrderStatus.REFUNDED
