"""End-to-end tests of the Vitals module's HTTP surface (recording a
reading against an open encounter, search/get) against a real Postgres —
see tests/conftest.py (skipped automatically if unreachable).
"""

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=owner_headers)
    assert created.status_code == 201
    return created.json()["patient"]["id"]


async def _register_walk_in(api_client: AsyncClient, owner_headers: dict[str, str], *, patient_id: str, branch_id: str) -> str:
    response = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["encounter"]["id"]


async def _cancel_encounter(api_client: AsyncClient, owner_headers: dict[str, str], *, encounter_id: str) -> None:
    response = await api_client.post(f"/api/v1/encounters/{encounter_id}/cancel", json={"reason": "test"}, headers=owner_headers)
    assert response.status_code == 200


# ---- Recording ----------------------------------------------------------------


async def test_nurse_can_record_vitals(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "VitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900001")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.post(
        "/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 78, "spo2": 98}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["encounter_id"] == encounter_id
    assert body["patient_id"] == patient_id
    assert body["recorded_by_role"] == "NURSE"
    assert body["heart_rate"] == 78


async def test_doctor_can_record_vitals(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorVitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900002")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "temperature_celsius": 37.2}, headers=headers)
    assert response.status_code == 201


async def test_owner_can_record_vitals(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OwnerVitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900003")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 80}, headers=owner_headers)
    assert response.status_code == 201


async def test_receptionist_cannot_record_vitals_by_default(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ReceptionistVitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900004")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 80}, headers=headers)
    assert response.status_code == 403


async def test_lab_staff_cannot_record_vitals(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "LabVitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900005")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    headers, _ = await login_as(role_code="LAB_STAFF")
    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 80}, headers=headers)
    assert response.status_code == 403


async def test_recording_against_a_nonexistent_encounter_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/vitals", json={"encounter_id": "00000000-0000-0000-0000-000000000000", "heart_rate": 80}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_recording_against_a_cancelled_encounter_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CancelledVitalsBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900006")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _cancel_encounter(api_client, owner_headers, encounter_id=encounter_id)

    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 80}, headers=owner_headers)
    assert response.status_code == 409


async def test_bmi_is_computed_from_weight_and_height(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "BmiBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900007")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post(
        "/api/v1/vitals", json={"encounter_id": encounter_id, "weight_kg": 70, "height_cm": 175}, headers=owner_headers
    )
    assert response.status_code == 201
    assert response.json()["bmi"] == pytest.approx(22.86, abs=0.01)


async def test_bmi_is_null_without_both_weight_and_height(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoBmiBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900008")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "weight_kg": 70}, headers=owner_headers)
    assert response.status_code == 201
    assert response.json()["bmi"] is None


# ---- Reading -------------------------------------------------------------------


async def test_receptionist_can_view_vitals_despite_not_recording_them(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ViewOnlyBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900009")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 75}, headers=owner_headers)

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.get(f"/api/v1/vitals?encounter_id={encounter_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_lab_staff_cannot_view_vitals(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="LAB_STAFF")
    response = await api_client.get("/api/v1/vitals", headers=headers)
    assert response.status_code == 403


async def test_search_filters_by_patient_across_encounters(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PatientHistoryBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919876900010")
    encounter_1 = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _cancel_encounter(api_client, owner_headers, encounter_id=encounter_1)
    encounter_2 = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_2, "heart_rate": 70}, headers=owner_headers)

    response = await api_client.get(f"/api/v1/vitals?patient_id={patient_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["encounter_id"] == encounter_2


async def test_get_nonexistent_vitals_reading_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/vitals/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404
