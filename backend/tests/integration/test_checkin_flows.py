"""End-to-end tests of the Check-in module's HTTP surface (walk-in
registration, checking in an existing appointment, no-show, encounter
lifecycle, and queue/token management) — against a real Postgres, see
tests/conftest.py (skipped automatically if unreachable).
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

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
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str
) -> str:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers
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


async def _book_appointment(
    api_client: AsyncClient, owner_headers: dict[str, str], *, patient_id: str, branch_id: str, doctor_id: str, scheduled_at: datetime
) -> str:
    created = await api_client.post(
        "/api/v1/appointments",
        json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id, "scheduled_at": scheduled_at.isoformat()},
        headers=owner_headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


# ---- Walk-in registration ---------------------------------------------------


async def test_receptionist_can_register_a_walk_in(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "Main")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876800001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800002")

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["appointment"]["source"] == "WALK_IN"
    assert body["appointment"]["status"] == "CHECKED_IN"
    assert body["encounter"]["status"] == "OPEN"
    assert body["encounter"]["appointment_id"] == body["appointment"]["id"]
    assert body["queue_token"]["status"] == "WAITING"
    assert body["queue_token"]["token_number"] == 1
    assert body["queue_token"]["encounter_id"] == body["encounter"]["id"]


async def test_walk_in_allows_no_doctor_assigned_yet(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoDoctorBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800003")

    response = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    assert response.status_code == 201
    assert response.json()["queue_token"]["doctor_id"] is None


async def test_nurse_cannot_register_a_walk_in(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NurseBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800004")

    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=headers)
    assert response.status_code == 403


async def test_walk_in_with_nonexistent_patient_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "BadPatientBranch")
    response = await api_client.post(
        "/api/v1/encounters/walk-in", json={"patient_id": "00000000-0000-0000-0000-000000000000", "branch_id": branch_id}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_walk_in_with_nonexistent_branch_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800005")
    response = await api_client.post(
        "/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": "00000000-0000-0000-0000-000000000000"}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_sequential_walk_ins_at_the_same_branch_get_incrementing_token_numbers(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "SequenceBranch")
    patient_a = await _create_patient(api_client, owner_headers, phone="+919876800006")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919876800007")

    first = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_a, "branch_id": branch_id}, headers=owner_headers)
    second = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_b, "branch_id": branch_id}, headers=owner_headers)
    assert first.json()["queue_token"]["token_number"] == 1
    assert second.json()["queue_token"]["token_number"] == 2


async def test_walk_ins_at_different_branches_each_start_their_own_sequence(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_a = await _create_branch(api_client, owner_headers, "SeqBranchA")
    branch_b = await _create_branch(api_client, owner_headers, "SeqBranchB")
    patient_a = await _create_patient(api_client, owner_headers, phone="+919876800008")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919876800009")

    resp_a = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_a, "branch_id": branch_a}, headers=owner_headers)
    resp_b = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_b, "branch_id": branch_b}, headers=owner_headers)
    assert resp_a.json()["queue_token"]["token_number"] == 1
    assert resp_b.json()["queue_token"]["token_number"] == 1


# ---- Check-in of an existing appointment ------------------------------------


async def test_receptionist_can_check_in_a_scheduled_appointment(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CheckInBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876800010")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800011")
    appointment_id = await _book_appointment(
        api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id, scheduled_at=_future_slot()
    )

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(f"/api/v1/encounters/{appointment_id}/check-in", headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["appointment"]["id"] == appointment_id
    assert body["appointment"]["status"] == "CHECKED_IN"
    assert body["encounter"]["appointment_id"] == appointment_id
    assert body["queue_token"]["doctor_id"] == doctor_id


async def test_cannot_check_in_the_same_appointment_twice(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleCheckInBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876800012")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800013")
    appointment_id = await _book_appointment(
        api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id, scheduled_at=_future_slot()
    )

    first = await api_client.post(f"/api/v1/encounters/{appointment_id}/check-in", headers=owner_headers)
    assert first.status_code == 201
    second = await api_client.post(f"/api/v1/encounters/{appointment_id}/check-in", headers=owner_headers)
    assert second.status_code == 409


async def test_checking_in_a_nonexistent_appointment_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/encounters/00000000-0000-0000-0000-000000000000/check-in", headers=owner_headers)
    assert response.status_code == 404


# ---- No-show -----------------------------------------------------------------


async def test_receptionist_can_mark_a_scheduled_appointment_no_show(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoShowBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876800014")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800015")
    appointment_id = await _book_appointment(
        api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id, scheduled_at=_future_slot()
    )

    response = await api_client.post(f"/api/v1/encounters/{appointment_id}/no-show", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "NO_SHOW"


async def test_cannot_mark_no_show_on_an_already_checked_in_appointment(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoShowConflictBranch")
    doctor_id = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919876800016")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800017")
    appointment_id = await _book_appointment(
        api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id, scheduled_at=_future_slot()
    )
    await api_client.post(f"/api/v1/encounters/{appointment_id}/check-in", headers=owner_headers)

    response = await api_client.post(f"/api/v1/encounters/{appointment_id}/no-show", headers=owner_headers)
    assert response.status_code == 409


# ---- Encounter read / cancel --------------------------------------------------


async def test_nurse_can_view_but_not_register_encounters(
    api_client: AsyncClient, owner_headers: dict[str, str], login_as
) -> None:
    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.get("/api/v1/encounters", headers=headers)
    assert response.status_code == 200


async def test_lab_staff_cannot_view_encounters(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="LAB_STAFF")
    response = await api_client.get("/api/v1/encounters", headers=headers)
    assert response.status_code == 403


async def test_get_nonexistent_encounter_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/encounters/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_cancelling_an_open_encounter_also_skips_its_queue_token(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CancelEncounterBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800018")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]
    token_id = walk_in.json()["queue_token"]["id"]

    response = await api_client.post(f"/api/v1/encounters/{encounter_id}/cancel", json={"reason": "wrong patient"}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    queue = await api_client.get("/api/v1/queue", headers=owner_headers)
    token = next(t for t in queue.json()["items"] if t["id"] == token_id)
    assert token["status"] == "SKIPPED"


async def test_cancelling_an_already_cancelled_encounter_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleCancelEncounterBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800019")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]

    first = await api_client.post(f"/api/v1/encounters/{encounter_id}/cancel", json={"reason": "x"}, headers=owner_headers)
    assert first.status_code == 200
    second = await api_client.post(f"/api/v1/encounters/{encounter_id}/cancel", json={"reason": "x"}, headers=owner_headers)
    assert second.status_code == 409


# ---- Queue / tokens ------------------------------------------------------------


async def test_call_next_transitions_the_earliest_waiting_token(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CallNextBranch")
    patient_a = await _create_patient(api_client, owner_headers, phone="+919876800020")
    patient_b = await _create_patient(api_client, owner_headers, phone="+919876800021")
    first = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_a, "branch_id": branch_id}, headers=owner_headers)
    await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_b, "branch_id": branch_id}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/queue/call-next?branch_id={branch_id}", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == first.json()["queue_token"]["id"]
    assert body["status"] == "CALLED"
    assert body["called_at"] is not None


async def test_call_next_with_no_waiting_tokens_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "EmptyQueueBranch")
    response = await api_client.post(f"/api/v1/queue/call-next?branch_id={branch_id}", headers=owner_headers)
    assert response.status_code == 404


async def test_valid_queue_token_status_chain(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "StatusChainBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800022")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    token_id = walk_in.json()["queue_token"]["id"]

    called = await api_client.patch(f"/api/v1/queue/{token_id}", json={"status": "CALLED"}, headers=owner_headers)
    assert called.status_code == 200
    in_progress = await api_client.patch(f"/api/v1/queue/{token_id}", json={"status": "IN_PROGRESS"}, headers=owner_headers)
    assert in_progress.status_code == 200
    done = await api_client.patch(f"/api/v1/queue/{token_id}", json={"status": "DONE"}, headers=owner_headers)
    assert done.status_code == 200
    assert done.json()["status"] == "DONE"


async def test_invalid_queue_token_transition_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "InvalidTransitionBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800023")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    token_id = walk_in.json()["queue_token"]["id"]

    # WAITING -> DONE skips the whole chain, not a legal transition.
    response = await api_client.patch(f"/api/v1/queue/{token_id}", json={"status": "DONE"}, headers=owner_headers)
    assert response.status_code == 409


async def test_updating_a_nonexistent_token_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch(
        "/api/v1/queue/00000000-0000-0000-0000-000000000000", json={"status": "CALLED"}, headers=owner_headers
    )
    assert response.status_code == 404


async def test_nurse_cannot_call_next_or_update_queue(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NurseQueueBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876800024")
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    token_id = walk_in.json()["queue_token"]["id"]

    headers, _ = await login_as(role_code="NURSE")
    call_next = await api_client.post(f"/api/v1/queue/call-next?branch_id={branch_id}", headers=headers)
    assert call_next.status_code == 403
    update = await api_client.patch(f"/api/v1/queue/{token_id}", json={"status": "CALLED"}, headers=headers)
    assert update.status_code == 403


async def test_nurse_can_view_the_queue(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.get("/api/v1/queue", headers=headers)
    assert response.status_code == 200
