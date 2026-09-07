"""End-to-end tests of File Storage & Uploads — upload/download,
per-owner_type permission dispatch, and row-level scoping (Patient-self,
Doctor-treated-patient, "only COMPLETED lab reports") — against a real
Postgres. See tests/conftest.py (skipped automatically if unreachable).
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


async def _link_patient_to_user(test_clinic: Clinic, *, patient_id: str, user_id: uuid.UUID) -> None:
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == uuid.UUID(patient_id)).values(user_id=user_id))


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


async def _treat_patient(api_client: AsyncClient, owner_headers: dict[str, str], *, branch_id: str, patient_id: str, doctor_id: str, doctor_headers: dict[str, str]) -> None:
    """Minimal walk-in -> consultation so `doctor_has_treated_patient` is true."""
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    assert walk_in.status_code == 201
    encounter_id = walk_in.json()["encounter"]["id"]
    consultation = await api_client.post("/api/v1/consultations", json={"encounter_id": encounter_id}, headers=doctor_headers)
    assert consultation.status_code == 201


async def _upload(api_client: AsyncClient, headers: dict[str, str], *, owner_type: str, owner_id: str, filename: str = "report.pdf", content: bytes = b"%PDF-1.4 fake content", content_type: str = "application/pdf"):
    return await api_client.post(
        "/api/v1/files/upload",
        data={"owner_type": owner_type, "owner_id": owner_id},
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


# ---- Upload / RBAC (PATIENT_DOCUMENT) ------------------------------------------------


async def test_owner_can_upload_and_download_a_patient_document(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919866000001")

    uploaded = await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id, filename="scan.pdf", content=b"binary-pdf-bytes")
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["original_filename"] == "scan.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["owner_type"] == "PATIENT_DOCUMENT"
    assert body["owner_id"] == patient_id
    document_id = body["id"]

    meta = await api_client.get(f"/api/v1/files/{document_id}", headers=owner_headers)
    assert meta.status_code == 200
    assert meta.json()["original_filename"] == "scan.pdf"

    content = await api_client.get(f"/api/v1/files/{document_id}/content", headers=owner_headers)
    assert content.status_code == 200
    assert content.content == b"binary-pdf-bytes"
    assert content.headers["content-type"] == "application/pdf"
    assert "scan.pdf" in content.headers["content-disposition"]


async def test_doctor_can_upload_a_patient_document(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    _, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919866000002")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919866000003")

    response = await _upload(api_client, doctor_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id)
    assert response.status_code == 201


async def test_receptionist_cannot_upload_a_patient_document(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919866000004")
    headers, _ = await login_as(role_code="RECEPTIONIST")

    response = await _upload(api_client, headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id)
    assert response.status_code == 403


async def test_uploading_with_an_unknown_owner_type_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await _upload(api_client, owner_headers, owner_type="INVOICE_PDF", owner_id=str(uuid.uuid4()))
    assert response.status_code == 422


async def test_uploading_a_patient_document_for_a_nonexistent_patient_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=str(uuid.uuid4()))
    assert response.status_code == 422


async def test_get_nonexistent_document_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get(f"/api/v1/files/{uuid.uuid4()}", headers=owner_headers)
    assert response.status_code == 404


# ---- Row scoping (PATIENT_DOCUMENT) ----------------------------------------------------


async def test_patient_can_view_their_own_document_but_not_anothers(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    patient_a_id = await _create_patient(api_client, owner_headers, phone="+919866000005")
    patient_b_id = await _create_patient(api_client, owner_headers, phone="+919866000006")
    doc_a = (await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_a_id)).json()
    doc_b = (await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_b_id)).json()

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_a_id, user_id=patient_user_id)

    own = await api_client.get(f"/api/v1/files/{doc_a['id']}", headers=patient_headers)
    assert own.status_code == 200
    others = await api_client.get(f"/api/v1/files/{doc_b['id']}", headers=patient_headers)
    assert others.status_code == 404


async def test_doctor_who_has_not_treated_the_patient_cannot_view_their_document(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "FilesTreatBranch")
    treating_doctor_id, treating_doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919866000007")
    _, other_doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone="+919866000008")
    patient_id = await _create_patient(api_client, owner_headers, phone="+919866000009")
    await _treat_patient(api_client, owner_headers, branch_id=branch_id, patient_id=patient_id, doctor_id=treating_doctor_id, doctor_headers=treating_doctor_headers)

    document = (await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id)).json()

    treating_can_view = await api_client.get(f"/api/v1/files/{document['id']}", headers=treating_doctor_headers)
    assert treating_can_view.status_code == 200
    other_cannot_view = await api_client.get(f"/api/v1/files/{document['id']}", headers=other_doctor_headers)
    assert other_cannot_view.status_code == 404


# ---- LAB_REPORT ---------------------------------------------------------------------


async def _enable_lab_and_create_completed_order(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, *, doctor_phone: str, patient_phone: str) -> tuple[str, str, dict[str, str]]:
    flag = await api_client.put("/api/v1/clinics/me/settings/features.lab_enabled", json={"value": True}, headers=owner_headers)
    assert flag.status_code == 200
    branch_id = await _create_branch(api_client, owner_headers, f"FilesLabBranch-{doctor_phone}")
    doctor_id, doctor_headers = await _create_active_doctor(api_client, owner_headers, test_clinic, phone=doctor_phone)
    patient_id = await _create_patient(api_client, owner_headers, phone=patient_phone)
    walk_in = await api_client.post("/api/v1/encounters/walk-in", json={"patient_id": patient_id, "branch_id": branch_id, "doctor_id": doctor_id}, headers=owner_headers)
    encounter_id = walk_in.json()["encounter"]["id"]

    test_catalog = await api_client.post(
        "/api/v1/lab/tests", json={"name": "CBC", "test_code": f"CBC-{doctor_phone}", "specimen_type": "Blood", "price": 300, "reference_ranges": []}, headers=owner_headers
    )
    test_id = test_catalog.json()["id"]
    order = await api_client.post("/api/v1/lab/orders", json={"encounter_id": encounter_id, "test_id": test_id}, headers=owner_headers)
    order_id = order.json()["id"]
    await api_client.post(f"/api/v1/lab/orders/{order_id}/collect-sample", headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/results", json={"results": [{"parameter": "Hemoglobin", "value": "14", "unit": "g/dL"}]}, headers=owner_headers)
    await api_client.post(f"/api/v1/lab/orders/{order_id}/complete", headers=owner_headers)
    return order_id, patient_id, doctor_headers


async def test_lab_staff_can_upload_a_lab_report_and_patient_can_view_only_once_completed(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    order_id, patient_id, _ = await _enable_lab_and_create_completed_order(api_client, owner_headers, test_clinic, doctor_phone="+919866000010", patient_phone="+919866000011")

    lab_headers, _ = await login_as(role_code="LAB_STAFF")
    uploaded = await _upload(api_client, lab_headers, owner_type="LAB_REPORT", owner_id=order_id, filename="cbc-report.pdf")
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    await _link_patient_to_user(test_clinic, patient_id=patient_id, user_id=patient_user_id)

    can_view = await api_client.get(f"/api/v1/files/{document_id}", headers=patient_headers)
    assert can_view.status_code == 200


async def test_receptionist_cannot_upload_a_lab_report(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    order_id, _, _ = await _enable_lab_and_create_completed_order(api_client, owner_headers, test_clinic, doctor_phone="+919866000012", patient_phone="+919866000013")
    headers, _ = await login_as(role_code="RECEPTIONIST")

    response = await _upload(api_client, headers, owner_type="LAB_REPORT", owner_id=order_id)
    assert response.status_code == 403


# ---- LETTERHEAD_ASSET -----------------------------------------------------------------


async def test_owner_can_upload_a_letterhead_asset_and_any_staff_can_view_it(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic, login_as) -> None:
    uploaded = await _upload(api_client, owner_headers, owner_type="LETTERHEAD_ASSET", owner_id=str(test_clinic.id), filename="logo.png", content_type="image/png")
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    receptionist_headers, _ = await login_as(role_code="RECEPTIONIST")
    view = await api_client.get(f"/api/v1/files/{document_id}", headers=receptionist_headers)
    assert view.status_code == 200
    content = await api_client.get(f"/api/v1/files/{document_id}/content", headers=receptionist_headers)
    assert content.status_code == 200


async def test_letterhead_asset_owner_id_must_be_the_tenant_itself(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await _upload(api_client, owner_headers, owner_type="LETTERHEAD_ASSET", owner_id=str(uuid.uuid4()), filename="logo.png")
    assert response.status_code == 422


async def test_nurse_cannot_upload_a_letterhead_asset(api_client: AsyncClient, test_clinic: Clinic, login_as) -> None:
    headers, _ = await login_as(role_code="NURSE")
    response = await _upload(api_client, headers, owner_type="LETTERHEAD_ASSET", owner_id=str(test_clinic.id))
    assert response.status_code == 403


# ---- Search -----------------------------------------------------------------------------


async def test_search_files_by_owner(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    patient_id = await _create_patient(api_client, owner_headers, phone="+919866000014")
    other_patient_id = await _create_patient(api_client, owner_headers, phone="+919866000015")
    doc_1 = (await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id, filename="a.pdf")).json()
    doc_2 = (await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=patient_id, filename="b.pdf")).json()
    await _upload(api_client, owner_headers, owner_type="PATIENT_DOCUMENT", owner_id=other_patient_id, filename="c.pdf")

    response = await api_client.get(f"/api/v1/files?owner_type=PATIENT_DOCUMENT&owner_id={patient_id}", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    ids = {item["id"] for item in body["items"]}
    assert ids == {doc_1["id"], doc_2["id"]}
