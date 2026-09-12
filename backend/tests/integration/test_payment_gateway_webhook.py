"""End-to-end tests of the Razorpay webhook endpoint — Phase 2 (Master
Handoff item 4, "webhook processing" / "payment failure" / "refund
states") — against a real Postgres. See tests/conftest.py (skipped
automatically if unreachable).

A `PaymentGatewayOrder` row is seeded directly via `platform_admin_session`
(bypassing HTTP) with `provider="razorpay"`, rather than going through the
real `POST .../book` flow with `payment_gateway_provider=razorpay` set —
that would require a genuine network call to Razorpay's Orders API with
real credentials, which no test environment has. This still exercises the
webhook handler's real DB-side logic (signature verification, idempotent
status transitions, tenant resolution from a bare `provider_order_id`)
end-to-end through the actual HTTP endpoint.
"""

import hashlib
import hmac
import json
import uuid

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.db import platform_admin_session
from app.modules.appointments.models import Appointment, AppointmentPaymentStatus, AppointmentSource
from app.modules.billing.models import PaymentGatewayOrder, PaymentGatewayOrderStatus
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WEBHOOK_SECRET = "test_webhook_secret"


def _sign(body: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _seed_pending_order(test_clinic: Clinic, *, branch_id, doctor_id, patient_id) -> tuple[str, str]:
    """Returns (appointment_id, provider_order_id)."""
    async with platform_admin_session() as session:
        appointment = Appointment(
            tenant_id=test_clinic.id, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id,
            source=AppointmentSource.ONLINE, scheduled_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            + __import__("datetime").timedelta(days=10),
            duration_minutes=15, payment_status=AppointmentPaymentStatus.PENDING,
        )
        session.add(appointment)
        await session.flush()

        provider_order_id = f"order_{uuid.uuid4().hex[:16]}"
        order = PaymentGatewayOrder(
            tenant_id=test_clinic.id, appointment_id=appointment.id, provider="razorpay",
            provider_order_id=provider_order_id, amount=100, currency="INR",
        )
        session.add(order)
        await session.flush()
        return str(appointment.id), provider_order_id


async def _create_branch_and_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic):
    branch = await api_client.post("/api/v1/branches", json={"name": "WebhookBranch"}, headers=owner_headers)
    doctor = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Doc", "phone": "+919000000050"}, headers=owner_headers,
    )
    patient = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": "+919000000051"}, headers=owner_headers)
    return branch.json()["id"], doctor.json()["doctor"]["user_id"], patient.json()["patient"]["id"]


async def test_payment_captured_webhook_confirms_the_booking(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", _WEBHOOK_SECRET)

    branch_id, doctor_id, patient_id = await _create_branch_and_doctor(api_client, owner_headers, test_clinic)
    appointment_id, provider_order_id = await _seed_pending_order(test_clinic, branch_id=branch_id, doctor_id=doctor_id, patient_id=patient_id)

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_abc123", "order_id": provider_order_id, "status": "captured"}}},
    }).encode("utf-8")

    response = await api_client.post(
        "/api/v1/billing/webhooks/razorpay", content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": _sign(body)},
    )
    assert response.status_code == 200

    appointment = await api_client.get(f"/api/v1/appointments/{appointment_id}", headers=owner_headers)
    assert appointment.json()["payment_status"] == "CONFIRMED"


async def test_payment_failed_webhook_marks_the_booking_failed(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", _WEBHOOK_SECRET)

    branch_id, doctor_id, patient_id = await _create_branch_and_doctor(api_client, owner_headers, test_clinic)
    appointment_id, provider_order_id = await _seed_pending_order(test_clinic, branch_id=branch_id, doctor_id=doctor_id, patient_id=patient_id)

    body = json.dumps({
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": "pay_failed1", "order_id": provider_order_id, "error_description": "Card declined"}}},
    }).encode("utf-8")

    response = await api_client.post(
        "/api/v1/billing/webhooks/razorpay", content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": _sign(body)},
    )
    assert response.status_code == 200

    appointment = await api_client.get(f"/api/v1/appointments/{appointment_id}", headers=owner_headers)
    assert appointment.json()["payment_status"] == "FAILED"


async def test_webhook_rejects_an_invalid_signature(
    api_client: AsyncClient, test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", _WEBHOOK_SECRET)

    body = json.dumps({"event": "payment.captured", "payload": {}}).encode("utf-8")
    response = await api_client.post(
        "/api/v1/billing/webhooks/razorpay", content=body,
        headers={"content-type": "application/json", "x-razorpay-signature": "not-the-real-signature"},
    )
    assert response.status_code == 401


async def test_webhook_is_idempotent_on_redelivery(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", _WEBHOOK_SECRET)

    branch_id, doctor_id, patient_id = await _create_branch_and_doctor(api_client, owner_headers, test_clinic)
    appointment_id, provider_order_id = await _seed_pending_order(test_clinic, branch_id=branch_id, doctor_id=doctor_id, patient_id=patient_id)

    body = json.dumps({
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_redeliver", "order_id": provider_order_id, "status": "captured"}}},
    }).encode("utf-8")
    headers = {"content-type": "application/json", "x-razorpay-signature": _sign(body)}

    first = await api_client.post("/api/v1/billing/webhooks/razorpay", content=body, headers=headers)
    second = await api_client.post("/api/v1/billing/webhooks/razorpay", content=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200

    appointment = await api_client.get(f"/api/v1/appointments/{appointment_id}", headers=owner_headers)
    assert appointment.json()["payment_status"] == "CONFIRMED"
