"""End-to-end tests of the Appointments module's HTTP surface (booking
only — see app/modules/appointments/models.py's module docstring for what
is deliberately out of scope), against a real Postgres — see
tests/conftest.py (skipped automatically if unreachable).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


def _future_slot(*, days: int = 2, hour: int = 10) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str, working_hours: dict | None = None
) -> str:
    created = await api_client.post(
        "/api/v1/doctors",
        json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS if working_hours is None else working_hours},
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


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


async def _link_patient_to_user(test_clinic: Clinic, *, patient_id: str, user_id: uuid.UUID) -> None:
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == uuid.UUID(patient_id)).values(user_id=user_id))


# ---- Create (staff-side) --------------------------------------------------


async def test_receptionist_can_book_an_appointment_for_a_patient(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "Main")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700002")

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "branch_id": branch_id,
            "doctor_id": doctor_id,
            "scheduled_at": _future_slot().isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "RECEPTIONIST"
    assert body["status"] == "SCHEDULED"


async def test_nurse_cannot_book_an_appointment(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "Nurse Branch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700003")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700004")

    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot().isoformat()},
        headers=headers,
    )
    assert response.status_code == 403


async def test_booking_with_a_nonexistent_branch_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700005")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700006")

    response = await api_client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "branch_id": "00000000-0000-0000-0000-000000000000",
            "doctor_id": doctor_id,
            "scheduled_at": _future_slot().isoformat(),
        },
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_booking_with_a_nonexistent_doctor_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoDoctorBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700007")

    response = await api_client.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "branch_id": branch_id,
            "doctor_id": "00000000-0000-0000-0000-000000000000",
            "scheduled_at": _future_slot().isoformat(),
        },
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_booking_outside_doctor_working_hours_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Working-hours enforcement defaults OFF (Settings.appointment_enforce_
    # working_hours — a deliberate pre-launch testing accommodation, see its
    # own docstring in app/core/config.py); force it on here since this
    # test's whole point is verifying that rule still works when a clinic
    # turns it back on.
    monkeypatch.setattr(get_settings(), "appointment_enforce_working_hours", True)
    branch_id = await _create_branch(api_client, owner_headers, "ClosedBranch")
    # No working_hours configured at all -> every day is unavailable (fail closed).
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700008", working_hours={})
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700009")

    response = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot().isoformat()},
        headers=owner_headers,
    )
    assert response.status_code == 409


async def test_double_booking_the_same_doctor_slot_conflicts(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OverlapBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700010")
    patient_a = await _create_patient(api_client, owner_headers, phone="+919876700011")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919876700012")
    slot = _future_slot(days=3, hour=11)

    first = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_a, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": slot.isoformat()},
        headers=owner_headers,
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_b, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": slot.isoformat()},
        headers=owner_headers,
    )
    assert second.status_code == 409


async def test_cancelled_appointment_frees_the_slot(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "FreedBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700013")
    patient_a = await _create_patient(api_client, owner_headers, phone="+919876700014")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919876700015")
    slot = _future_slot(days=4, hour=11)

    first = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_a, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": slot.isoformat()},
        headers=owner_headers,
    )
    appointment_id = first.json()["id"]
    await api_client.post(f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "no longer needed"}, headers=owner_headers)

    second = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_b, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": slot.isoformat()},
        headers=owner_headers,
    )
    assert second.status_code == 201


# ---- Create (patient self-booking) --------------------------------------------


async def test_patient_can_book_their_own_appointment(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "SelfBookBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700020")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700021")

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_id, user_id=patient_user_id)

    response = await api_client.post(
        "/api/v1/appointments/me",
        json={"branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=5).isoformat()},
        headers=patient_headers,
    )
    assert response.status_code == 201
    assert response.json()["source"] == "ONLINE"
    assert response.json()["patient_id"] == patient_id


async def test_patient_without_a_linked_record_cannot_book(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "UnlinkedBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700022")

    patient_headers, _ = await login_as(role_code="PATIENT")
    response = await api_client.post(
        "/api/v1/appointments/me",
        json={"branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=6).isoformat()},
        headers=patient_headers,
    )
    assert response.status_code == 404


# ---- Read / search ----------------------------------------------------------


async def test_doctor_only_sees_their_own_appointments(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorViewBranch")
    doctor_a_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700030")
    doctor_b_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700031")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700032")

    await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_a_id, "scheduled_at": _future_slot(days=7).isoformat()},
        headers=owner_headers,
    )
    await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_b_id, "scheduled_at": _future_slot(days=8).isoformat()},
        headers=owner_headers,
    )

    doctor_a_headers = {"Authorization": f"Bearer {(await api_client.post('/api/v1/auth/staff/login', json={'clinic_slug': test_clinic.slug, 'identifier': '+919876700030', 'password': 'password-123'})).json()['access_token']}"}
    response = await api_client.get(f"/api/v1/appointments?doctor_id={doctor_b_id}", headers=doctor_a_headers)
    assert response.status_code == 200
    # doctor_id filter is overridden server-side to the caller's own id.
    assert all(a["doctor_id"] == doctor_a_id for a in response.json()["items"])


async def test_lab_staff_cannot_view_appointments(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="LAB_STAFF")
    response = await api_client.get("/api/v1/appointments", headers=headers)
    assert response.status_code == 403


async def test_get_nonexistent_appointment_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/appointments/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


# ---- Reschedule / cancel --------------------------------------------------------


async def test_owner_can_reschedule_an_appointment(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "RescheduleBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700040")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700041")

    created = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=9).isoformat()},
        headers=owner_headers,
    )
    appointment_id = created.json()["id"]
    new_slot = _future_slot(days=10, hour=14)

    response = await api_client.patch(
        f"/api/v1/appointments/{appointment_id}", json={"scheduled_at": new_slot.isoformat()}, headers=owner_headers
    )
    assert response.status_code == 200
    # Compare parsed instants, not raw strings — the API serializes UTC
    # with a "Z" suffix while Python's isoformat() uses "+00:00" for the
    # same instant.
    assert datetime.fromisoformat(response.json()["scheduled_at"].replace("Z", "+00:00")) == new_slot


async def test_cannot_reschedule_a_cancelled_appointment(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CancelledRescheduleBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700042")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700043")

    created = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=11).isoformat()},
        headers=owner_headers,
    )
    appointment_id = created.json()["id"]
    await api_client.post(f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "x"}, headers=owner_headers)

    response = await api_client.patch(
        f"/api/v1/appointments/{appointment_id}", json={"duration_minutes": 30}, headers=owner_headers
    )
    assert response.status_code == 409


async def test_cancelling_twice_conflicts(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleCancelBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700044")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876700045")

    created = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=12).isoformat()},
        headers=owner_headers,
    )
    appointment_id = created.json()["id"]
    first = await api_client.post(f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "x"}, headers=owner_headers)
    assert first.status_code == 200

    second = await api_client.post(f"/api/v1/appointments/{appointment_id}/cancel", json={"reason": "x"}, headers=owner_headers)
    assert second.status_code == 409


async def test_patient_can_cancel_their_own_appointment_but_not_anothers(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PatientCancelBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876700046")

    patient_a_id = await _create_patient(api_client, owner_headers, phone="+919876700047")
    patient_b_id = await _create_patient(api_client, owner_headers, phone="+919876700048")

    patient_a_headers, patient_a_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_a_id, user_id=patient_a_user_id)

    created_for_a = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_a_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=13).isoformat()},
        headers=owner_headers,
    )
    created_for_b = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_b_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": _future_slot(days=14).isoformat()},
        headers=owner_headers,
    )

    own_cancel = await api_client.post(
        f"/api/v1/appointments/me/{created_for_a.json()['id']}/cancel", json={"reason": "changed my mind"}, headers=patient_a_headers
    )
    assert own_cancel.status_code == 200

    other_cancel = await api_client.post(
        f"/api/v1/appointments/me/{created_for_b.json()['id']}/cancel", json={"reason": "not mine"}, headers=patient_a_headers
    )
    assert other_cancel.status_code == 404
