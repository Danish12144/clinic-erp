"""End-to-end tests of the Consultation and Prescription modules' HTTP
surface (start/update/complete a consultation, encounter state transitions,
issue/supersede a prescription, the letterhead-driven print view) against a
real Postgres — see tests/conftest.py (skipped automatically if unreachable).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.db import tenant_session
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")

_WIDE_OPEN_HOURS = {day: {"open": "00:00", "close": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str, *, address: str | None = None, phone: str | None = None) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name, "address": address, "phone": phone}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _create_active_doctor(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, phone: str) -> tuple[str, dict[str, str]]:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Doc", "phone": phone, "working_hours": _WIDE_OPEN_HOURS}, headers=owner_headers
    )
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


async def _register_walk_in(api_client: AsyncClient, owner_headers: dict[str, str], *, patient_id: str, branch_id: str, doctor_id: str | None = None) -> str:
    payload = {"patient_id": patient_id, "branch_id": branch_id}
    if doctor_id:
        payload["doctor_id"] = doctor_id
    response = await api_client.post("/api/v1/encounters/walk-in", json=payload, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["encounter"]["id"]


async def _start_consultation(api_client: AsyncClient, headers: dict[str, str], *, encounter_id: str) -> dict:
    response = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id, "chief_complaint": "Fever"}, headers=headers)
    assert response.status_code == 201
    return response.json()


def _one_item(**overrides) -> dict:
    item = {"medicine_name_freetext": "Paracetamol 500mg", "dosage": "1 tab", "frequency": "BID", "duration": "5 days", "route": "oral", "prescribed_quantity": 10}
    item.update(overrides)
    return item


# ---- Consultation lifecycle -----------------------------------------------------


async def test_doctor_can_start_a_consultation_and_it_transitions_the_encounter(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ConsultBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000002")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)

    body = await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)
    assert body["doctor_id"] == doctor_id
    assert body["started_at"] is not None
    assert body["ended_at"] is None

    encounters = await api_client.get(f"/api/v1/encounters?branch_id={branch_id}", headers=owner_headers)
    matched = next(e for e in encounters.json()["items"] if e["id"] == encounter_id)
    assert matched["status"] == "IN_CONSULTATION"


async def test_owner_can_also_start_a_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OwnerConsultBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000003")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert response.status_code == 201


async def test_receptionist_cannot_start_a_consultation(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "RecConsultBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000004")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=headers)
    assert response.status_code == 403


async def test_starting_a_second_consultation_for_the_same_encounter_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DupeConsultBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000005")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)

    response = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=owner_headers)
    assert response.status_code == 409


async def test_starting_a_consultation_on_a_nonexistent_encounter_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/consultations", json={"encounter_id": "00000000-0000-0000-0000-000000000000"}, headers=owner_headers)
    assert response.status_code == 422


async def test_doctor_can_update_own_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "UpdateBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000006")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000007")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    consultation = await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)

    response = await api_client.patch(
        f"/api/v1/consultations/{consultation['id']}", json={"diagnosis_text": "Viral fever", "icd10_code": "J11"}, headers=doctor_headers
    )
    assert response.status_code == 200
    assert response.json()["diagnosis_text"] == "Viral fever"


async def test_another_doctor_cannot_update_someones_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CrossDoctorBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000008")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000009")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000010")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    consultation = await _start_consultation(api_client, doctor_a_headers, encounter_id=encounter_id)

    response = await api_client.patch(f"/api/v1/consultations/{consultation['id']}", json={"diagnosis_text": "Hijack"}, headers=doctor_b_headers)
    assert response.status_code == 403


async def test_completing_a_consultation_transitions_the_encounter_to_completed(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "CompleteBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000011")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    consultation = await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)

    response = await api_client.post(f"/api/v1/consultations/{consultation['id']}/complete", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["ended_at"] is not None

    encounters = await api_client.get(f"/api/v1/encounters?branch_id={branch_id}", headers=owner_headers)
    matched = next(e for e in encounters.json()["items"] if e["id"] == encounter_id)
    assert matched["status"] == "COMPLETED"


async def test_completing_an_already_completed_consultation_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleCompleteBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000012")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    consultation = await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    await api_client.post(f"/api/v1/consultations/{consultation['id']}/complete", headers=owner_headers)

    response = await api_client.post(f"/api/v1/consultations/{consultation['id']}/complete", headers=owner_headers)
    assert response.status_code == 409


async def test_cannot_edit_a_completed_consultation(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "EditAfterCompleteBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000013")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    consultation = await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    await api_client.post(f"/api/v1/consultations/{consultation['id']}/complete", headers=owner_headers)

    response = await api_client.patch(f"/api/v1/consultations/{consultation['id']}", json={"diagnosis_text": "too late"}, headers=owner_headers)
    assert response.status_code == 409


async def test_nurse_can_view_but_not_start_consultations(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.get("/api/v1/consultations", headers=headers)
    assert response.status_code == 200
    write = await api_client.post("/api/v1/consultations", json={"encounter_id": "00000000-0000-0000-0000-000000000000"}, headers=headers)
    assert write.status_code == 403


async def test_lab_staff_cannot_view_consultations(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="LAB_STAFF")
    response = await api_client.get("/api/v1/consultations", headers=headers)
    assert response.status_code == 403


async def test_doctor_search_is_scoped_to_own_consultations(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "ScopedSearchBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000014")
    doctor_b_id, _ = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000015")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000016")
    encounter_a = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    encounter_b = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_b_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_b)

    response = await api_client.get(f"/api/v1/consultations?doctor_id={doctor_b_id}", headers=doctor_a_headers)
    assert response.status_code == 200
    assert all(c["doctor_id"] == doctor_a_id for c in response.json()["items"])


async def test_doctor_get_of_anothers_consultation_is_404(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "Get404Branch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000017")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000018")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000019")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    consultation = await _start_consultation(api_client, doctor_a_headers, encounter_id=encounter_id)

    response = await api_client.get(f"/api/v1/consultations/{consultation['id']}", headers=doctor_b_headers)
    assert response.status_code == 404


# ---- Prescriptions -------------------------------------------------------------


async def test_issuing_a_prescription_requires_a_started_consultation(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "NoConsultBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000020")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)

    response = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    assert response.status_code == 422


async def test_doctor_can_issue_a_prescription_for_own_consultation(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "IssueBranch")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000021")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000022")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)

    response = await api_client.post(
        "/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item(), _one_item(medicine_name_freetext="Cetirizine")]}, headers=doctor_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["doctor_id"] == doctor_id
    assert body["supersedes_prescription_id"] is None
    assert len(body["items"]) == 2
    assert body["items"][0]["dispensed_quantity"] == 0


async def test_doctor_cannot_issue_a_prescription_for_another_doctors_consultation(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "IssueCrossBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000023")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877000024")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000025")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    await _start_consultation(api_client, doctor_a_headers, encounter_id=encounter_id)

    response = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=doctor_b_headers)
    assert response.status_code == 403


async def test_nurse_cannot_issue_a_prescription(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    response = await api_client.post(
        "/api/v1/prescriptions", json={"encounter_id": "00000000-0000-0000-0000-000000000000", "items": [_one_item()]}, headers=headers
    )
    assert response.status_code == 403


async def test_superseding_a_prescription_creates_a_new_one_and_leaves_the_original_untouched(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "SupersedeBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000026")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    original = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    original_id = original.json()["id"]

    superseded = await api_client.post(
        f"/api/v1/prescriptions/{original_id}/supersede", json={"encounter_id": encounter_id, "items": [_one_item(dosage="2 tab")]}, headers=owner_headers
    )
    assert superseded.status_code == 201
    assert superseded.json()["supersedes_prescription_id"] == original_id

    refetched_original = await api_client.get(f"/api/v1/prescriptions/{original_id}", headers=owner_headers)
    assert refetched_original.json()["items"][0]["dosage"] == "1 tab"


async def test_superseding_an_already_superseded_prescription_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "DoubleSupersedeBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000027")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    original = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    original_id = original.json()["id"]
    await api_client.post(f"/api/v1/prescriptions/{original_id}/supersede", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/prescriptions/{original_id}/supersede", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    assert response.status_code == 409


async def test_get_nonexistent_prescription_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/prescriptions/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


# ---- Print view / letterhead integration ----------------------------------------


async def test_prescription_print_view_digital_includes_a_header(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PrintDigitalBranch", address="12 MG Road", phone="+911234567890")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000028")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    prescription_id = created.json()["id"]

    response = await api_client.get(f"/api/v1/prescriptions/{prescription_id}/print?mode=DIGITAL", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["letterhead"]["mode"] == "DIGITAL"
    assert body["letterhead"]["header"] is not None
    assert body["letterhead"]["header"]["address"] == "12 MG Road"
    assert body["letterhead"]["top_margin_mm"] == 0.0


async def test_prescription_print_view_physical_omits_header_and_uses_margins(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PrintPhysicalBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877000029")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    prescription_id = created.json()["id"]

    response = await api_client.get(f"/api/v1/prescriptions/{prescription_id}/print?mode=PHYSICAL", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["letterhead"]["mode"] == "PHYSICAL"
    assert body["letterhead"]["header"] is None
    assert body["letterhead"]["footer"] is None
    assert body["letterhead"]["top_margin_mm"] == 40.0


# ---- Prescription PDF (File Storage integration) --------------------------------------


async def _link_patient_to_user(test_clinic: Clinic, *, patient_id: str, user_id: uuid.UUID) -> None:
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == uuid.UUID(patient_id)).values(user_id=user_id))


async def test_issuing_a_prescription_generates_a_downloadable_pdf(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PdfBranch", address="1 PDF Ave", phone="+911100000000")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877100001")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877100002")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_id)
    await _start_consultation(api_client, doctor_headers, encounter_id=encounter_id)

    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=doctor_headers)
    assert created.status_code == 201
    body = created.json()
    assert body["pdf_document_id"] is not None
    assert body["pdf_download_url"] == f"/api/v1/files/{body['pdf_document_id']}/content"

    content = await api_client.get(body["pdf_download_url"], headers=doctor_headers)
    assert content.status_code == 200
    assert content.headers["content-type"] == "application/pdf"
    assert content.content.startswith(b"%PDF")


async def test_get_prescription_includes_the_pdf_link(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PdfGetBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877100003")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    prescription_id = created.json()["id"]

    fetched = await api_client.get(f"/api/v1/prescriptions/{prescription_id}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["pdf_document_id"] == created.json()["pdf_document_id"]


async def test_superseding_a_prescription_generates_a_distinct_new_pdf(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "SupersedePdfBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877100004")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    original = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    original_id = original.json()["id"]

    superseded = await api_client.post(f"/api/v1/prescriptions/{original_id}/supersede", json={"encounter_id": encounter_id, "items": [_one_item(dosage="2 tab")]}, headers=owner_headers)
    assert superseded.status_code == 201
    assert superseded.json()["pdf_document_id"] != original.json()["pdf_document_id"]

    # The original's own PDF is untouched — still resolvable independently.
    original_refetched = await api_client.get(f"/api/v1/prescriptions/{original_id}", headers=owner_headers)
    assert original_refetched.json()["pdf_document_id"] == original.json()["pdf_document_id"]


async def test_patient_can_view_and_download_their_own_prescription_pdf(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "PatientPdfBranch")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877100005")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_id)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=owner_headers)
    body = created.json()

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_id, user_id=patient_user_id)

    fetched = await api_client.get(f"/api/v1/prescriptions/{body['id']}", headers=patient_headers)
    assert fetched.status_code == 200
    content = await api_client.get(body["pdf_download_url"], headers=patient_headers)
    assert content.status_code == 200
    assert content.content.startswith(b"%PDF")


async def test_patient_cannot_view_or_download_another_patients_prescription(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OtherPatientPdfBranch")
    patient_a_id = await _create_patient(api_client, owner_headers, phone="+919877100006")
    patient_b_id = await _create_patient(api_client, owner_headers, phone="+919877100007")
    encounter_a = await _register_walk_in(api_client, owner_headers, patient_id=patient_a_id, branch_id=branch_id)
    await _start_consultation(api_client, owner_headers, encounter_id=encounter_a)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_a, "items": [_one_item()]}, headers=owner_headers)
    body = created.json()

    patient_b_headers, patient_b_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_b_id, user_id=patient_b_user_id)

    fetched = await api_client.get(f"/api/v1/prescriptions/{body['id']}", headers=patient_b_headers)
    assert fetched.status_code == 404
    content = await api_client.get(body["pdf_download_url"], headers=patient_b_headers)
    assert content.status_code == 404


async def test_doctor_who_does_not_own_the_prescription_cannot_download_its_pdf(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "OtherDoctorPdfBranch")
    doctor_a_id, doctor_a_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877100008")
    _, doctor_b_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919877100009")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919877100010")
    encounter_id = await _register_walk_in(api_client, owner_headers, patient_id=patient_id, branch_id=branch_id, doctor_id=doctor_a_id)
    await _start_consultation(api_client, doctor_a_headers, encounter_id=encounter_id)
    created = await api_client.post("/api/v1/prescriptions", json={"encounter_id": encounter_id, "items": [_one_item()]}, headers=doctor_a_headers)
    body = created.json()

    content = await api_client.get(body["pdf_download_url"], headers=doctor_b_headers)
    assert content.status_code == 404
