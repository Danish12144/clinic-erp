"""End-to-end tests of Notification Templates & Outbox Integration —
template CRUD, preview rendering, log inspection, RBAC, and the outbox
dispatch wired into Appointments/Billing/Lab/CRM's own business triggers —
against a real Postgres. See tests/conftest.py (skipped automatically if
unreachable).
"""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


def _template_payload(**overrides) -> dict:
    payload = {
        "template_key": "APPOINTMENT_BOOKED", "channel": "WHATSAPP",
        "body_text": "Hi {{patient_name}}, see you at {{clinic_name}} on {{appointment_time}}!",
        "variables": ["patient_name", "clinic_name", "appointment_time"],
    }
    payload.update(overrides)
    return payload


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str, fee: float | None = 500) -> tuple[str, dict[str, str]]:
    payload = {"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}
    if fee is not None:
        payload["consultation_fee"] = fee
    created = await api_client.post("/api/v1/doctors", json=payload, headers=owner_headers)
    assert created.status_code == 201
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    accept = await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"})
    assert accept.status_code == 200
    login = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": phone, "password": "password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return user_id, headers


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str, first_name: str = "Pat") -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": first_name, "phone": phone}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


# ---- Template CRUD / RBAC -------------------------------------------------------


async def test_owner_can_create_list_and_update_a_template(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/notifications/templates", json=_template_payload(), headers=owner_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["template_key"] == "APPOINTMENT_BOOKED"
    assert body["is_active"] is True
    template_id = body["id"]

    listed = await api_client.get("/api/v1/notifications/templates", headers=owner_headers)
    assert listed.status_code == 200
    assert any(t["id"] == template_id for t in listed.json()["items"])

    updated = await api_client.patch(f"/api/v1/notifications/templates/{template_id}", json={"is_active": False}, headers=owner_headers)
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False


async def test_duplicate_channel_and_key_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="DUPE_KEY"), headers=owner_headers)
    assert first.status_code == 201
    second = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="DUPE_KEY"), headers=owner_headers)
    assert second.status_code == 409


async def test_same_key_different_channel_is_allowed(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="MULTI_CHANNEL", channel="WHATSAPP"), headers=owner_headers)
    assert first.status_code == 201
    second = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="MULTI_CHANNEL", channel="SMS"), headers=owner_headers)
    assert second.status_code == 201


async def test_updating_a_nonexistent_template_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch("/api/v1/notifications/templates/00000000-0000-0000-0000-000000000000", json={"is_active": False}, headers=owner_headers)
    assert response.status_code == 404


async def test_receptionist_and_doctor_can_view_but_not_manage_templates(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    created = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="RBAC_VIEW_KEY"), headers=owner_headers)
    template_id = created.json()["id"]

    for role in ("RECEPTIONIST", "DOCTOR"):
        headers, _ = await login_as(role_code=role)
        read = await api_client.get("/api/v1/notifications/templates", headers=headers)
        assert read.status_code == 200, role
        create = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key=f"BLOCKED_{role}"), headers=headers)
        assert create.status_code == 403, role
        update = await api_client.patch(f"/api/v1/notifications/templates/{template_id}", json={"is_active": False}, headers=headers)
        assert update.status_code == 403, role
        preview = await api_client.post("/api/v1/notifications/send-preview", json={"template_id": template_id}, headers=headers)
        assert preview.status_code == 403, role


async def test_nurse_has_zero_access(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    read = await api_client.get("/api/v1/notifications/templates", headers=headers)
    assert read.status_code == 403
    logs = await api_client.get("/api/v1/notifications/logs", headers=headers)
    assert logs.status_code == 403


# ---- Preview --------------------------------------------------------------------


async def test_send_preview_renders_with_sample_data(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="PREVIEW_KEY"), headers=owner_headers)
    template_id = created.json()["id"]

    response = await api_client.post(
        "/api/v1/notifications/send-preview",
        json={"template_id": template_id, "sample_data": {"patient_name": "Jane Doe", "clinic_name": "Sunrise Clinic", "appointment_time": "2026-09-10 10:00"}},
        headers=owner_headers,
    )
    assert response.status_code == 200
    assert response.json()["rendered_body"] == "Hi Jane Doe, see you at Sunrise Clinic on 2026-09-10 10:00!"


async def test_send_preview_with_missing_sample_data_brackets_the_placeholder(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="PARTIAL_PREVIEW_KEY"), headers=owner_headers)
    template_id = created.json()["id"]

    response = await api_client.post("/api/v1/notifications/send-preview", json={"template_id": template_id}, headers=owner_headers)
    assert response.status_code == 200
    assert "[patient_name]" in response.json()["rendered_body"]


async def test_send_preview_for_a_nonexistent_template_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/notifications/send-preview", json={"template_id": "00000000-0000-0000-0000-000000000000"}, headers=owner_headers)
    assert response.status_code == 404


async def test_send_preview_does_not_write_a_communication_log(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/notifications/templates", json=_template_payload(template_key="NO_SIDE_EFFECT_KEY"), headers=owner_headers)
    template_id = created.json()["id"]

    before = await api_client.get("/api/v1/notifications/logs", headers=owner_headers)
    before_count = before.json()["total"]

    await api_client.post("/api/v1/notifications/send-preview", json={"template_id": template_id}, headers=owner_headers)

    after = await api_client.get("/api/v1/notifications/logs", headers=owner_headers)
    assert after.json()["total"] == before_count


# ---- Outbox dispatch integration (Appointments/Billing/Lab/CRM) ---------------------


async def test_booking_an_appointment_queues_a_notification_with_default_body(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NotifyApptBranch")
    doctor_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000002", first_name="Alice")

    scheduled_at = "2026-09-15T10:00:00+00:00"
    booked = await api_client.post(
        "/api/v1/appointments", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": scheduled_at},
        headers=owner_headers,
    )
    assert booked.status_code == 201

    logs = await api_client.get(f"/api/v1/notifications/logs?patient_id={patient_id}", headers=owner_headers)
    assert logs.status_code == 200
    entries = logs.json()["items"]
    assert len(entries) == 1
    assert entries[0]["status"] == "QUEUED"
    assert entries[0]["channel"] == "WHATSAPP"
    assert "Alice" in entries[0]["rendered_body"]
    assert entries[0]["template_id"] is None  # no clinic override exists yet — built-in default was used


async def test_a_clinic_configured_template_overrides_the_default_body(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    await api_client.post(
        "/api/v1/notifications/templates",
        json={"template_key": "APPOINTMENT_BOOKED", "channel": "WHATSAPP", "body_text": "CUSTOM MESSAGE for {{patient_name}}", "variables": ["patient_name"]},
        headers=owner_headers,
    )
    branch_id = await _create_branch(api_client, owner_headers, "OverrideBranch")
    doctor_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000003")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000004", first_name="Bob")

    booked = await api_client.post(
        "/api/v1/appointments", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": "2026-09-16T11:00:00+00:00"},
        headers=owner_headers,
    )
    assert booked.status_code == 201

    logs = await api_client.get(f"/api/v1/notifications/logs?patient_id={patient_id}", headers=owner_headers)
    entries = logs.json()["items"]
    assert len(entries) == 1
    assert entries[0]["rendered_body"] == "CUSTOM MESSAGE for Bob"
    assert entries[0]["template_id"] is not None


async def test_recording_a_payment_queues_a_bill_receipt_but_a_refund_does_not(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NotifyBillingBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000005", first_name="Carol")
    invoice = await api_client.post(
        "/api/v1/billing/invoices",
        json={"branch_id": branch_id, "patient_id": patient_id, "line_items": [{"source_type": "OTHER", "description": "Item", "quantity": 1, "unit_price": 500}]},
        headers=owner_headers,
    )
    invoice_id = invoice.json()["id"]
    await api_client.post(f"/api/v1/billing/invoices/{invoice_id}/issue", headers=owner_headers)

    payment = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": 500, "method": "CASH"}, headers=owner_headers)
    assert payment.status_code == 201

    refund = await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_id, "amount": -100, "method": "CASH"}, headers=owner_headers)
    assert refund.status_code == 201

    logs = await api_client.get(f"/api/v1/notifications/logs?patient_id={patient_id}", headers=owner_headers)
    entries = logs.json()["items"]
    assert len(entries) == 1  # only the real payment dispatched a receipt, not the refund
    assert "500" in entries[0]["rendered_body"]


async def test_completing_a_lab_order_queues_a_result_ready_notification(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    flag = await api_client.put("/api/v1/clinics/me/settings/features.lab_enabled", json={"value": True}, headers=owner_headers)
    assert flag.status_code == 200

    branch_id = await _create_branch(api_client, owner_headers, "NotifyLabBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000006")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000007", first_name="Dave")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]

    test_catalog = await api_client.post(
        "/api/v1/lab/tests", json={"name": "CBC", "test_code": "CBC1", "specimen_type": "Blood", "turnaround_hours": 24, "price": 300, "reference_ranges": []},
        headers=owner_headers,
    )
    test_id = test_catalog.json()["id"]
    order = await api_client.post("/api/v1/lab/orders", json={"encounter_id": encounter_id, "test_id": test_id}, headers=owner_headers)
    order_id = order.json()["id"]
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)
    await api_client.post(
        f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Hemoglobin", "value": "14", "unit": "g/dL"}]}, headers=owner_headers
    )
    completed = await api_client.post(f"/api/v1/lab/orders/{order_id}/complete", headers=owner_headers)
    assert completed.status_code == 200

    logs = await api_client.get(f"/api/v1/notifications/logs?patient_id={patient_id}", headers=owner_headers)
    entries = logs.json()["items"]
    assert len(entries) == 1
    assert "Dave" in entries[0]["rendered_body"]
    assert "CBC" in entries[0]["rendered_body"]


async def test_creating_a_follow_up_queues_a_rendered_reminder(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000008", first_name="Eve")
    due_at = (date.today() + timedelta(days=3)).isoformat() + "T09:00:00+00:00"

    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": due_at}, headers=owner_headers)
    assert created.status_code == 201

    logs = await api_client.get(f"/api/v1/notifications/logs?patient_id={patient_id}", headers=owner_headers)
    entries = logs.json()["items"]
    assert len(entries) == 1
    assert "Eve" in entries[0]["rendered_body"]


# ---- Logs filters ----------------------------------------------------------------


async def test_logs_filter_by_channel_and_status(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "LogFilterBranch")
    doctor_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000009")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000010", first_name="Frank")
    await api_client.post(
        "/api/v1/appointments", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": "2026-09-17T09:00:00+00:00"},
        headers=owner_headers,
    )

    by_channel = await api_client.get("/api/v1/notifications/logs?channel=WHATSAPP", headers=owner_headers)
    assert by_channel.status_code == 200
    assert any(entry["patient_id"] == patient_id for entry in by_channel.json()["items"])

    by_wrong_channel = await api_client.get("/api/v1/notifications/logs?channel=EMAIL", headers=owner_headers)
    assert all(entry["patient_id"] != patient_id for entry in by_wrong_channel.json()["items"])

    by_status = await api_client.get("/api/v1/notifications/logs?status=QUEUED", headers=owner_headers)
    assert any(entry["patient_id"] == patient_id for entry in by_status.json()["items"])
