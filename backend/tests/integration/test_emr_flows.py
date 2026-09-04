"""End-to-end tests of the Patient EMR Timeline & Medical Documents HTTP
surface against a real Postgres — see tests/conftest.py (skipped
automatically if unreachable).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.db import tenant_session
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


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


async def _full_visit(
    api_client: AsyncClient, owner_headers: dict[str, str], *, branch_id: str, patient_id: str, doctor_id: str, doctor_headers: dict[str, str],
    diagnosis: str = "Viral fever", complete: bool = True,
) -> dict:
    """Walk-in -> consultation -> vitals -> diagnosis -> prescription ->
    (optionally) complete. Returns a dict of the created ids."""
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    assert walk_in.status_code == 201
    encounter_id = walk_in.json()["encounter"]["id"]

    vitals = await api_client.post("/api/v1/vitals", json={"encounter_id": encounter_id, "heart_rate": 80}, headers=doctor_headers)
    assert vitals.status_code == 201

    consultation = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id, "chief_complaint": "Fever"}, headers=doctor_headers)
    assert consultation.status_code == 201
    consultation_id = consultation.json()["id"]

    diag = await api_client.patch(f"/api/v1/consultations/{consultation_id}", json={"diagnosis_text": diagnosis, "icd10_code": "J11"}, headers=doctor_headers)
    assert diag.status_code == 200

    prescription = await api_client.post(
        "/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [{"medicine_name_freetext": "Paracetamol", "prescribed_quantity": 10}]}, headers=doctor_headers
    )
    assert prescription.status_code == 201

    if complete:
        completed = await api_client.post(f"/api/v1/consultations/{consultation_id}/complete", headers=doctor_headers)
        assert completed.status_code == 200

    return {"encounter_id": encounter_id, "consultation_id": consultation_id, "prescription_id": prescription.json()["id"]}


# ---- Timeline ---------------------------------------------------------------


async def test_owner_sees_full_emr_timeline(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "EmrBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000002")
    await _full_visit(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id, doctor_headers=doctor_headers)

    response = await api_client.get(f"/api/v1/patients/{patient_id}/emr", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == patient_id
    assert len(body["visits"]) == 1
    assert body["visits"][0]["diagnosis_text"] == "Viral fever"
    assert body["visits"][0]["doctor_id"] == doctor_id
    assert len(body["prescriptions"]) == 1
    assert body["prescriptions"][0]["items"][0]["medicine_name_freetext"] == "Paracetamol"
    assert len(body["vitals"]) == 1
    assert body["vitals"][0]["heart_rate"] == 80


async def test_doctor_who_treated_patient_can_view_timeline(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoctorEmrBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000003")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000004")
    await _full_visit(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id, doctor_headers=doctor_headers)

    response = await api_client.get(f"/api/v1/patients/{patient_id}/emr", headers=doctor_headers)
    assert response.status_code == 200
    assert len(response.json()["visits"]) == 1


async def test_doctor_who_never_treated_patient_gets_404(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "UntreatedBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000005")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000006")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000007")
    await _full_visit(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_a_id, doctor_headers=doctor_a_headers)

    response = await api_client.get(f"/api/v1/patients/{patient_id}/emr", headers=doctor_b_headers)
    assert response.status_code == 404


async def test_patient_can_view_own_timeline_but_not_anothers(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PatientEmrBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000008")
    patient_a_id = await _create_patient(api_client, owner_headers, phone="+919880000009")
    patient_b_id = await _create_patient(api_client, owner_headers, phone="+919880000010")
    await _full_visit(api_client, owner_headers, branch_id=branch_id, patient_id=patient_a_id, doctor_id=doctor_id, doctor_headers=doctor_headers)

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == uuid.UUID(patient_a_id)).values(user_id=patient_user_id))

    own = await api_client.get(f"/api/v1/patients/{patient_a_id}/emr", headers=patient_headers)
    assert own.status_code == 200
    other = await api_client.get(f"/api/v1/patients/{patient_b_id}/emr", headers=patient_headers)
    assert other.status_code == 404


async def test_receptionist_and_nurse_have_no_emr_access(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000011")
    for role in ("RECEPTIONIST", "NURSE", "LAB_STAFF", "PHARMACY_STAFF"):
        headers, _ = await login_as(role_code=role)
        response = await api_client.get(f"/api/v1/patients/{patient_id}/emr", headers=headers)
        assert response.status_code == 403


async def test_emr_timeline_for_nonexistent_patient_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/patients/00000000-0000-0000-0000-000000000000/emr", headers=owner_headers)
    assert response.status_code == 404


async def test_date_range_excludes_visits_outside_the_window(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DateRangeBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000012")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000013")
    await _full_visit(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id, doctor_headers=doctor_headers)

    future_from = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    future_to = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    response = await api_client.get(f"/api/v1/patients/{patient_id}/emr", params={"date_from": future_from, "date_to": future_to}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["visits"] == []
    assert response.json()["vitals"] == []


# ---- Medical documents ----------------------------------------------------------


async def test_owner_and_doctor_can_upload_documents(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000014")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000015")

    owner_upload = await api_client.post(
        f"/api/v1/patients/{patient_id}/documents",
        json={"document_type": "LAB_REPORT", "title": "CBC Report", "storage_key": "s3://bucket/cbc.pdf", "mime_type": "application/pdf"},
        headers=owner_headers,
    )
    assert owner_upload.status_code == 201
    assert owner_upload.json()["document_type"] == "LAB_REPORT"

    doctor_upload = await api_client.post(
        f"/api/v1/patients/{patient_id}/documents", json={"document_type": "XRAY", "title": "Chest X-Ray", "storage_key": "s3://bucket/xray.png"}, headers=doctor_headers
    )
    assert doctor_upload.status_code == 201


async def test_receptionist_cannot_upload_documents(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000016")
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        f"/api/v1/patients/{patient_id}/documents", json={"document_type": "OTHER", "title": "x", "storage_key": "s3://bucket/x.pdf"}, headers=headers
    )
    assert response.status_code == 403


async def test_uploading_for_a_nonexistent_patient_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/patients/00000000-0000-0000-0000-000000000000/documents",
        json={"document_type": "OTHER", "title": "x", "storage_key": "s3://bucket/x.pdf"}, headers=owner_headers,
    )
    assert response.status_code == 422


async def test_documents_appear_in_search_and_timeline(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000017")
    await api_client.post(
        f"/api/v1/patients/{patient_id}/documents", json={"document_type": "SCAN", "title": "MRI Scan", "storage_key": "s3://bucket/mri.pdf"}, headers=owner_headers
    )

    search = await api_client.get(f"/api/v1/patients/{patient_id}/documents", headers=owner_headers)
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["title"] == "MRI Scan"

    timeline = await api_client.get(f"/api/v1/patients/{patient_id}/emr", headers=owner_headers)
    assert len(timeline.json()["documents"]) == 1


async def test_doctor_cannot_search_documents_for_an_untreated_patient(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    _, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919880000018")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000019")
    await api_client.post(
        f"/api/v1/patients/{patient_id}/documents", json={"document_type": "OTHER", "title": "x", "storage_key": "s3://bucket/x.pdf"}, headers=owner_headers
    )

    response = await api_client.get(f"/api/v1/patients/{patient_id}/documents", headers=doctor_headers)
    assert response.status_code == 404


async def test_get_nonexistent_document_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919880000020")
    response = await api_client.get(f"/api/v1/patients/{patient_id}/documents/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404
