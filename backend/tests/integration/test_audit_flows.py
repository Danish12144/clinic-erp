"""End-to-end tests of the Audit Logging module — PRD-ARCHITECTURE.md §14.
Verifies both the read endpoint (`GET /api/v1/audit-logs`, Owner-only) and
that other modules' mutating endpoints actually call
`app.modules.audit.service.record` — not a unit test of `record()` in
isolation, since the point of this module is other modules using it
correctly.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


async def test_owner_can_read_the_audit_log(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await api_client.post(
        "/api/v1/patients", json={"first_name": "Audited", "phone": "+919000077701"}, headers=owner_headers
    )

    response = await api_client.get("/api/v1/audit-logs", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_non_owner_cannot_read_the_audit_log(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.get("/api/v1/audit-logs", headers=headers)
    assert response.status_code == 403


async def test_patient_create_is_audited_with_before_and_after(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Priya", "phone": "+919000077702"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    response = await api_client.get(f"/api/v1/audit-logs?entity_type=patient&entity_id={patient_id}", headers=owner_headers)
    assert response.status_code == 200
    entries = response.json()["items"]
    assert any(e["action"] == "patient.create" and e["before"] is None and e["after"]["first_name"] == "Priya" for e in entries)


async def test_patient_update_is_audited_with_before_and_after(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Rohit", "phone": "+919000077703"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    await api_client.patch(f"/api/v1/patients/{patient_id}", json={"blood_group": "O+"}, headers=owner_headers)

    response = await api_client.get(f"/api/v1/audit-logs?entity_type=patient&entity_id={patient_id}", headers=owner_headers)
    entries = response.json()["items"]
    update_entry = next(e for e in entries if e["action"] == "patient.update")
    assert update_entry["before"]["blood_group"] is None
    assert update_entry["after"]["blood_group"] == "O+"
    assert update_entry["actor_role"] == "OWNER"


async def test_patient_soft_delete_is_audited_with_null_after(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Gone", "phone": "+919000077704"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    await api_client.delete(f"/api/v1/patients/{patient_id}", headers=owner_headers)

    response = await api_client.get(f"/api/v1/audit-logs?entity_type=patient&entity_id={patient_id}", headers=owner_headers)
    entries = response.json()["items"]
    delete_entry = next(e for e in entries if e["action"] == "patient.soft_delete")
    assert delete_entry["after"] is None
    assert delete_entry["before"]["first_name"] == "Gone"


async def test_doctor_lifecycle_actions_are_audited(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Meera", "phone": "+919000077705"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    await api_client.post(f"/api/v1/doctors/{user_id}/deactivate", headers=owner_headers)
    await api_client.post(f"/api/v1/doctors/{user_id}/reactivate", headers=owner_headers)

    response = await api_client.get(f"/api/v1/audit-logs?entity_type=doctor&entity_id={user_id}", headers=owner_headers)
    actions = {e["action"] for e in response.json()["items"]}
    assert actions == {"doctor.create", "doctor.deactivate", "doctor.reactivate"}


async def test_staff_create_is_audited(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "Kavya", "phone": "+919000077706"}, headers=owner_headers
    )
    user_id = created.json()["staff"]["user_id"]

    response = await api_client.get(f"/api/v1/audit-logs?entity_type=staff&entity_id={user_id}", headers=owner_headers)
    entries = response.json()["items"]
    assert any(e["action"] == "staff.create" for e in entries)


async def test_audit_log_filters_by_actor(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    me = await api_client.get("/api/v1/auth/me", headers=owner_headers)
    owner_user_id = me.json()["user"]["id"]

    await api_client.post("/api/v1/patients", json={"first_name": "ByActor", "phone": "+919000077707"}, headers=owner_headers)

    response = await api_client.get(f"/api/v1/audit-logs?actor_user_id={owner_user_id}", headers=owner_headers)
    assert response.status_code == 200
    entries = response.json()["items"]
    assert len(entries) >= 1
    assert all(e["actor_user_id"] == owner_user_id for e in entries)
