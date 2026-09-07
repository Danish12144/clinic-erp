"""End-to-end tests of the Lead Pipeline / CRM Funnel HTTP surface (status
workflow, interaction logging, patient conversion, RBAC, audit trail)
against a real Postgres — see tests/conftest.py (skipped automatically if
unreachable).
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


def _lead_payload(**overrides) -> dict:
    payload = {"first_name": "Jane", "last_name": "Doe", "phone": "+919876500001", "email": "jane.doe@example.com", "source": "WEBSITE"}
    payload.update(overrides)
    return payload


async def _create_lead(api_client: AsyncClient, headers: dict[str, str], **overrides) -> str:
    response = await api_client.post("/api/v1/leads", json=_lead_payload(**overrides), headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


# ---- Create / RBAC ------------------------------------------------------------------


async def test_owner_can_create_and_read_a_lead(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/leads", json=_lead_payload(), headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "Jane"
    assert body["status"] == "NEW"
    assert body["source"] == "WEBSITE"
    assert body["converted_patient_id"] is None

    fetched = await api_client.get(f"/api/v1/leads/{body['id']}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "jane.doe@example.com"


async def test_receptionist_has_full_crud_access(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    created = await api_client.post("/api/v1/leads", json=_lead_payload(first_name="Ravi"), headers=headers)
    assert created.status_code == 201
    lead_id = created.json()["id"]

    read = await api_client.get(f"/api/v1/leads/{lead_id}", headers=headers)
    assert read.status_code == 200

    updated = await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "CONTACTED"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["status"] == "CONTACTED"


async def test_doctor_is_read_only(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="DoctorReadLead")
    headers, _ = await login_as(role_code="DOCTOR")

    read = await api_client.get("/api/v1/leads", headers=headers)
    assert read.status_code == 200
    read_one = await api_client.get(f"/api/v1/leads/{lead_id}", headers=headers)
    assert read_one.status_code == 200

    create = await api_client.post("/api/v1/leads", json=_lead_payload(), headers=headers)
    assert create.status_code == 403
    update = await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "CONTACTED"}, headers=headers)
    assert update.status_code == 403
    interaction = await api_client.post(f"/api/v1/leads/{lead_id}/interactions", json={"interaction_type": "CALL"}, headers=headers)
    assert interaction.status_code == 403
    convert = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=headers)
    assert convert.status_code == 403


async def test_other_roles_have_zero_access(api_client: AsyncClient, login_as) -> None:
    for role in ("NURSE", "LAB_STAFF", "PHARMACY_STAFF", "OTHER_STAFF"):
        headers, _ = await login_as(role_code=role)
        read = await api_client.get("/api/v1/leads", headers=headers)
        assert read.status_code == 403, role
        create = await api_client.post("/api/v1/leads", json=_lead_payload(), headers=headers)
        assert create.status_code == 403, role


async def test_assigning_to_a_nonexistent_user_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/leads", json=_lead_payload(assigned_to_user_id="00000000-0000-0000-0000-000000000000"), headers=owner_headers
    )
    assert response.status_code == 422


async def test_reassigning_to_a_nonexistent_user_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="ReassignLead")
    response = await api_client.patch(
        f"/api/v1/leads/{lead_id}", json={"assigned_to_user_id": "00000000-0000-0000-0000-000000000000"}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_get_nonexistent_lead_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/leads/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_updating_a_nonexistent_lead_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch("/api/v1/leads/00000000-0000-0000-0000-000000000000", json={"status": "CONTACTED"}, headers=owner_headers)
    assert response.status_code == 404


# ---- Status workflow ----------------------------------------------------------------


async def test_status_can_move_through_the_pipeline(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="PipelineLead")
    for new_status in ("CONTACTED", "APPOINTMENT_SCHEDULED"):
        response = await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": new_status}, headers=owner_headers)
        assert response.status_code == 200
        assert response.json()["status"] == new_status


async def test_status_can_move_to_lost(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="LostLead")
    response = await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "LOST"}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "LOST"


async def test_patch_cannot_set_status_to_converted_directly(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="NoDirectConvertLead")
    response = await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "CONVERTED"}, headers=owner_headers)
    assert response.status_code == 422

    unchanged = await api_client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers)
    assert unchanged.json()["status"] == "NEW"
    assert unchanged.json()["converted_patient_id"] is None


async def test_notes_and_assignment_update_independently_of_status(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    _, receptionist_id = await login_as(role_code="RECEPTIONIST")
    lead_id = await _create_lead(api_client, owner_headers, first_name="AssignmentLead")

    response = await api_client.patch(
        f"/api/v1/leads/{lead_id}", json={"notes": "Called twice, no answer", "assigned_to_user_id": str(receptionist_id)}, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "Called twice, no answer"
    assert response.json()["assigned_to_user_id"] == str(receptionist_id)
    assert response.json()["status"] == "NEW"  # untouched


# ---- Interactions ----------------------------------------------------------------


async def test_logging_an_interaction(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="InteractionLead")
    response = await api_client.post(
        f"/api/v1/leads/{lead_id}/interactions", json={"interaction_type": "CALL", "outcome": "Interested", "notes": "Will visit Saturday"}, headers=owner_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["interaction_type"] == "CALL"
    assert body["outcome"] == "Interested"
    assert body["lead_id"] == lead_id


async def test_logging_an_interaction_against_a_nonexistent_lead_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/leads/00000000-0000-0000-0000-000000000000/interactions", json={"interaction_type": "NOTE"}, headers=owner_headers
    )
    assert response.status_code == 404


async def test_receptionist_can_log_an_interaction(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="ReceptionistInteractionLead")
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(f"/api/v1/leads/{lead_id}/interactions", json={"interaction_type": "WHATSAPP"}, headers=headers)
    assert response.status_code == 201


# ---- Conversion ----------------------------------------------------------------------


async def test_converting_a_lead_creates_a_linked_patient(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="ConvertMe", last_name="Lead", phone="+919876500099", email="convertme@example.com")
    await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "CONTACTED"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={"gender": "Female", "address": "12 Clinic Road"}, headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    patient_id = body["patient_id"]
    assert body["lead"]["status"] == "CONVERTED"
    assert body["lead"]["converted_patient_id"] == patient_id

    patient = await api_client.get(f"/api/v1/patients/{patient_id}", headers=owner_headers)
    assert patient.status_code == 200
    patient_body = patient.json()
    assert patient_body["first_name"] == "ConvertMe"
    assert patient_body["last_name"] == "Lead"
    assert patient_body["phone"] == "+919876500099"
    assert patient_body["email"] == "convertme@example.com"
    assert patient_body["gender"] == "Female"
    assert patient_body["address"] == "12 Clinic Road"

    lead_after = await api_client.get(f"/api/v1/leads/{lead_id}", headers=owner_headers)
    assert lead_after.json()["status"] == "CONVERTED"
    assert lead_after.json()["converted_patient_id"] == patient_id


async def test_converting_an_already_converted_lead_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="DoubleConvertLead", phone="+919876500098")
    first = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=owner_headers)
    assert first.status_code == 200

    second = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=owner_headers)
    assert second.status_code == 409


async def test_converting_a_lost_lead_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="LostConvertLead", phone="+919876500097")
    await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "LOST"}, headers=owner_headers)

    response = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=owner_headers)
    assert response.status_code == 409


async def test_converting_a_lead_with_no_contact_details_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/leads", json={"first_name": "NoContact"}, headers=owner_headers)
    assert response.status_code == 201
    lead_id = response.json()["id"]

    convert = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=owner_headers)
    assert convert.status_code == 422


async def test_converting_a_nonexistent_lead_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/leads/00000000-0000-0000-0000-000000000000/convert", json={}, headers=owner_headers)
    assert response.status_code == 404


# ---- Search filters ----------------------------------------------------------------


async def test_search_filters_by_status_and_source(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    website_id = await _create_lead(api_client, owner_headers, first_name="WebsiteLead", source="WEBSITE", phone="+919876500011")
    referral_id = await _create_lead(api_client, owner_headers, first_name="ReferralLead", source="REFERRAL", phone="+919876500012")
    await api_client.patch(f"/api/v1/leads/{referral_id}", json={"status": "CONTACTED"}, headers=owner_headers)

    by_source = await api_client.get("/api/v1/leads?source=WEBSITE", headers=owner_headers)
    assert by_source.status_code == 200
    ids = {l["id"] for l in by_source.json()["items"]}
    assert website_id in ids
    assert referral_id not in ids

    by_status = await api_client.get("/api/v1/leads?status=CONTACTED", headers=owner_headers)
    assert by_status.status_code == 200
    status_ids = {l["id"] for l in by_status.json()["items"]}
    assert referral_id in status_ids
    assert website_id not in status_ids


async def test_search_filters_by_assigned_staff(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    _, receptionist_id = await login_as(role_code="RECEPTIONIST")
    assigned_id = await _create_lead(api_client, owner_headers, first_name="AssignedFilterLead", assigned_to_user_id=str(receptionist_id), phone="+919876500013")
    unassigned_id = await _create_lead(api_client, owner_headers, first_name="UnassignedFilterLead", phone="+919876500014")

    response = await api_client.get(f"/api/v1/leads?assigned_to_user_id={receptionist_id}", headers=owner_headers)
    assert response.status_code == 200
    ids = {l["id"] for l in response.json()["items"]}
    assert assigned_id in ids
    assert unassigned_id not in ids


async def test_search_filters_by_date_range(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="DateRangeLead", phone="+919876500015")

    future_only = await api_client.get(
        "/api/v1/leads", params={"date_from": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, headers=owner_headers
    )
    assert future_only.status_code == 200
    assert all(l["id"] != lead_id for l in future_only.json()["items"])

    all_time = await api_client.get(
        "/api/v1/leads", params={"date_from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}, headers=owner_headers
    )
    assert any(l["id"] == lead_id for l in all_time.json()["items"])


# ---- Audit trail ----------------------------------------------------------------------


async def test_lead_lifecycle_is_audited(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    lead_id = await _create_lead(api_client, owner_headers, first_name="AuditedLead", phone="+919876500016")
    await api_client.patch(f"/api/v1/leads/{lead_id}", json={"status": "CONTACTED"}, headers=owner_headers)
    await api_client.post(f"/api/v1/leads/{lead_id}/interactions", json={"interaction_type": "CALL"}, headers=owner_headers)
    convert = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=owner_headers)
    patient_id = convert.json()["patient_id"]

    logs = await api_client.get("/api/v1/audit-logs", headers=owner_headers)
    assert logs.status_code == 200
    lead_actions = {entry["action"] for entry in logs.json()["items"] if entry["entity_id"] == lead_id}
    assert {"lead.create", "lead.update", "lead_interaction.create", "lead.convert"} <= lead_actions

    patient_actions = {entry["action"] for entry in logs.json()["items"] if entry["entity_id"] == patient_id}
    assert "patient.create" in patient_actions
