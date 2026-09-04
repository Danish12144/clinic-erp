"""End-to-end tests of the CRM & Follow-ups HTTP surface (schema, status
transitions, the stubbed reminder outbox, RBAC/scoping) against a real
Postgres — see tests/conftest.py (skipped automatically if unreachable).
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str) -> tuple[str, dict[str, str]]:
    created = await api_client.post("/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers)
    assert created.status_code == 201
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    accept = await api_client.post("/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"})
    assert accept.status_code == 200
    login = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": phone, "password": "password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return user_id, headers


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


def _future(days: int = 3) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days: int = 3) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ---- Creation ---------------------------------------------------------------------


async def test_receptionist_can_schedule_a_follow_up(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300001")
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future(), "reason": "Suture removal"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["reason"] == "Suture removal"
    assert body["reminder"]["status"] == "QUEUED"
    assert body["reminder"]["channel"] == "WHATSAPP"


async def test_doctor_can_schedule_their_own_follow_up(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300002")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300003")
    response = await api_client.post(
        "/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future(), "reason": "Chronic review"}, headers=doctor_headers
    )
    assert response.status_code == 201
    assert response.json()["doctor_id"] == doctor_id


async def test_doctor_id_is_forced_to_self_even_if_another_is_supplied(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300004")
    doctor_b_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300005")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300006")

    response = await api_client.post(
        "/api/v1/crm/follow-ups", json={"patient_id": patient_id, "doctor_id": doctor_b_id, "due_at": _future()}, headers=doctor_a_headers
    )
    assert response.status_code == 201
    assert response.json()["doctor_id"] == doctor_a_id


async def test_nurse_lab_and_pharmacy_have_no_crm_access(api_client: AsyncClient, login_as) -> None:
    for role in ("NURSE", "LAB_STAFF", "PHARMACY_STAFF"):
        headers, _ = await login_as(role_code=role)
        response = await api_client.get("/api/v1/crm/follow-ups", headers=headers)
        assert response.status_code == 403


async def test_creating_for_a_nonexistent_patient_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/crm/follow-ups", json={"patient_id": "00000000-0000-0000-0000-000000000000", "due_at": _future()}, headers=owner_headers
    )
    assert response.status_code == 422


# ---- Status transitions -----------------------------------------------------------


async def test_full_status_lifecycle_and_reminder_sync(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300007")
    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=owner_headers)
    follow_up_id = created.json()["id"]

    sent = await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "SENT"}, headers=owner_headers)
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT"
    assert sent.json()["reminder"]["status"] == "SENT"
    assert sent.json()["reminder"]["sent_at"] is not None

    confirmed = await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "CONFIRMED"}, headers=owner_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"


async def test_invalid_transition_from_terminal_status_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300008")
    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=owner_headers)
    follow_up_id = created.json()["id"]
    await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "CANCELLED"}, headers=owner_headers)

    response = await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "SENT"}, headers=owner_headers)
    assert response.status_code == 409


async def test_invalid_status_value_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300009")
    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=owner_headers)
    follow_up_id = created.json()["id"]

    response = await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "BOGUS"}, headers=owner_headers)
    assert response.status_code == 422


# ---- Overdue sweep + filters --------------------------------------------------------


async def test_past_due_follow_up_becomes_overdue_on_read(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300010")
    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _past()}, headers=owner_headers)
    follow_up_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"  # not yet swept at creation time

    refetched = await api_client.get(f"/api/v1/crm/follow-ups/{follow_up_id}", headers=owner_headers)
    assert refetched.status_code == 200
    assert refetched.json()["status"] == "OVERDUE"


async def test_overdue_filter_returns_only_overdue_items(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300011")
    overdue_created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _past()}, headers=owner_headers)
    overdue_id = overdue_created.json()["id"]
    future_created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=owner_headers)
    future_id = future_created.json()["id"]

    response = await api_client.get("/api/v1/crm/follow-ups?overdue=true", headers=owner_headers)
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()["items"]}
    assert overdue_id in ids
    assert future_id not in ids


async def test_search_filters_by_status_and_patient(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_a = await _create_patient(api_client, owner_headers, phone="+919883300012")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919883300013")
    follow_up_a = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_a, "due_at": _future()}, headers=owner_headers)
    await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_b, "due_at": _future()}, headers=owner_headers)

    response = await api_client.get(f"/api/v1/crm/follow-ups?patient_id={patient_a}", headers=owner_headers)
    assert response.status_code == 200
    ids = {f["id"] for f in response.json()["items"]}
    assert ids == {follow_up_a.json()["id"]}

    status_filtered = await api_client.get("/api/v1/crm/follow-ups?status=PENDING", headers=owner_headers)
    assert status_filtered.status_code == 200
    assert status_filtered.json()["total"] >= 2


# ---- Doctor row-scoping -------------------------------------------------------------


async def test_doctor_cannot_see_or_update_another_doctors_follow_up(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300014")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300015")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300016")

    created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=doctor_a_headers)
    follow_up_id = created.json()["id"]

    get_response = await api_client.get(f"/api/v1/crm/follow-ups/{follow_up_id}", headers=doctor_b_headers)
    assert get_response.status_code == 404

    update_response = await api_client.patch(f"/api/v1/crm/follow-ups/{follow_up_id}/status", json={"status": "SENT"}, headers=doctor_b_headers)
    assert update_response.status_code == 403


async def test_doctor_search_is_scoped_to_own_follow_ups(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300017")
    doctor_b_id, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300018")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300019")

    await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=doctor_a_headers)
    await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=doctor_b_headers)

    # Doctor A requests doctor_id=B explicitly — must be silently overridden.
    response = await api_client.get(f"/api/v1/crm/follow-ups?doctor_id={doctor_b_id}", headers=doctor_a_headers)
    assert response.status_code == 200
    assert all(f["doctor_id"] == doctor_a_id for f in response.json()["items"])


async def test_owner_sees_all_doctors_follow_ups(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300020")
    doctor_b_id, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919883300021")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919883300022")

    created_a = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=doctor_a_headers)
    created_b = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_id, "due_at": _future()}, headers=doctor_b_headers)

    response = await api_client.get("/api/v1/crm/follow-ups", headers=owner_headers)
    ids = {f["id"] for f in response.json()["items"]}
    assert created_a.json()["id"] in ids
    assert created_b.json()["id"] in ids


async def test_get_nonexistent_follow_up_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/crm/follow-ups/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404
