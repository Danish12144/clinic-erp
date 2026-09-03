"""End-to-end tests of the Patient Management module's HTTP surface,
against a real Postgres — see tests/conftest.py (skipped automatically if
unreachable).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.db import tenant_session
from app.modules.patients.models import Patient

pytestmark = pytest.mark.usefixtures("require_db")


# ---- Create ---------------------------------------------------------------


async def test_receptionist_can_create_a_patient_and_gets_an_auto_generated_mrn(
    api_client: AsyncClient, login_as
) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/patients",
        json={"first_name": "Asha", "last_name": "Verma", "phone": "+919876543210"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["patient"]["first_name"] == "Asha"
    assert body["patient"]["mrn"].startswith("MRN-")
    assert body["possible_duplicates"] == []


async def test_doctor_cannot_register_a_patient(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.post(
        "/api/v1/patients", json={"first_name": "Asha", "phone": "+919876543210"}, headers=headers
    )
    assert response.status_code == 403


async def test_creating_with_an_explicit_duplicate_mrn_conflicts(api_client: AsyncClient, owner_headers) -> None:
    first = await api_client.post(
        "/api/v1/patients", json={"first_name": "A", "phone": "+919000000001", "mrn": "MRN-CUSTOM-001"}, headers=owner_headers
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v1/patients", json={"first_name": "B", "phone": "+919000000002", "mrn": "MRN-CUSTOM-001"}, headers=owner_headers
    )
    assert second.status_code == 409


async def test_auto_generated_mrns_increment_within_the_same_tenant(api_client: AsyncClient, owner_headers) -> None:
    first = await api_client.post("/api/v1/patients", json={"first_name": "A", "phone": "+919000000011"}, headers=owner_headers)
    second = await api_client.post("/api/v1/patients", json={"first_name": "B", "phone": "+919000000012"}, headers=owner_headers)

    mrn_a = first.json()["patient"]["mrn"]
    mrn_b = second.json()["patient"]["mrn"]
    assert mrn_a != mrn_b


async def test_create_flags_possible_duplicate_by_phone(api_client: AsyncClient, owner_headers) -> None:
    await api_client.post("/api/v1/patients", json={"first_name": "Ravi", "phone": "+919111111111"}, headers=owner_headers)

    second = await api_client.post(
        "/api/v1/patients", json={"first_name": "Ravi K", "phone": "+919111111111"}, headers=owner_headers
    )

    # The new record is still created — this is a warning, not a block.
    assert second.status_code == 201
    assert len(second.json()["possible_duplicates"]) == 1
    assert second.json()["possible_duplicates"][0]["phone"] == "+919111111111"


async def test_create_flags_possible_duplicate_by_name_and_dob(api_client: AsyncClient, owner_headers) -> None:
    await api_client.post(
        "/api/v1/patients",
        json={"first_name": "Meera", "last_name": "Iyer", "date_of_birth": "1990-05-15", "email": "meera1@example.com"},
        headers=owner_headers,
    )

    second = await api_client.post(
        "/api/v1/patients",
        json={"first_name": "Meera", "last_name": "Iyer", "date_of_birth": "1990-05-15", "email": "meera2@example.com"},
        headers=owner_headers,
    )

    assert len(second.json()["possible_duplicates"]) == 1


# ---- Read / search ----------------------------------------------------------


async def test_get_patient_by_id(api_client: AsyncClient, owner_headers) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Kiran", "phone": "+919222222222"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    response = await api_client.get(f"/api/v1/patients/{patient_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "Kiran"


async def test_get_nonexistent_patient_is_404(api_client: AsyncClient, owner_headers) -> None:
    response = await api_client.get("/api/v1/patients/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_search_by_exact_phone(api_client: AsyncClient, owner_headers) -> None:
    await api_client.post("/api/v1/patients", json={"first_name": "Deepa", "phone": "+919333333333"}, headers=owner_headers)
    await api_client.post("/api/v1/patients", json={"first_name": "Neha", "phone": "+919444444444"}, headers=owner_headers)

    response = await api_client.get("/api/v1/patients?phone=%2B919333333333", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["first_name"] == "Deepa"


async def test_search_by_fuzzy_name(api_client: AsyncClient, owner_headers) -> None:
    await api_client.post(
        "/api/v1/patients", json={"first_name": "Siddharth", "last_name": "Rao", "phone": "+919555555555"}, headers=owner_headers
    )

    response = await api_client.get("/api/v1/patients?q=Sidharth Rao", headers=owner_headers)
    assert response.status_code == 200
    assert any(p["first_name"] == "Siddharth" for p in response.json()["items"])


async def test_lab_staff_can_search_patients_but_not_register_one(api_client: AsyncClient, login_as) -> None:
    """PRD §3 matrix grants Lab Staff read access to patient search — the
    gap where migration 0001 forgot this grant was fixed in migration
    0004, discovered while building this module."""
    headers, _ = await login_as(role_code="LAB_STAFF")

    read = await api_client.get("/api/v1/patients", headers=headers)
    assert read.status_code == 200

    write = await api_client.post("/api/v1/patients", json={"first_name": "X", "phone": "+919666666666"}, headers=headers)
    assert write.status_code == 403


async def test_pharmacy_staff_can_search_patients(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="PHARMACY_STAFF")
    response = await api_client.get("/api/v1/patients", headers=headers)
    assert response.status_code == 200


async def test_other_staff_cannot_search_patients_by_default(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="OTHER_STAFF")
    response = await api_client.get("/api/v1/patients", headers=headers)
    assert response.status_code == 403


async def test_search_pagination(api_client: AsyncClient, owner_headers) -> None:
    for i in range(5):
        await api_client.post(
            "/api/v1/patients", json={"first_name": f"Bulk{i}", "phone": f"+9198765430{i:02d}"}, headers=owner_headers
        )

    response = await api_client.get("/api/v1/patients?limit=2&offset=0", headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["total"] >= 5


# ---- Update / delete ----------------------------------------------------------


async def test_owner_can_update_patient_demographics(api_client: AsyncClient, owner_headers) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Anita", "phone": "+919777777777"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    updated = await api_client.patch(
        f"/api/v1/patients/{patient_id}", json={"blood_group": "B+", "allergies": ["Penicillin"]}, headers=owner_headers
    )
    assert updated.status_code == 200
    assert updated.json()["blood_group"] == "B+"
    assert updated.json()["allergies"] == ["Penicillin"]


async def test_update_with_empty_body_is_rejected(api_client: AsyncClient, owner_headers) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Vikram", "phone": "+919888888888"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    response = await api_client.patch(f"/api/v1/patients/{patient_id}", json={}, headers=owner_headers)
    assert response.status_code == 422


async def test_nurse_cannot_update_patient_demographics(api_client: AsyncClient, owner_headers, login_as) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Rohit", "phone": "+919999999900"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    nurse_headers, _ = await login_as(role_code="NURSE")
    response = await api_client.patch(f"/api/v1/patients/{patient_id}", json={"blood_group": "A+"}, headers=nurse_headers)
    assert response.status_code == 403


async def test_soft_delete_hides_patient_from_default_search_but_not_from_include_deleted(
    api_client: AsyncClient, owner_headers
) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "Farewell", "phone": "+919999999911"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    deleted = await api_client.delete(f"/api/v1/patients/{patient_id}", headers=owner_headers)
    assert deleted.status_code == 204

    gone = await api_client.get(f"/api/v1/patients/{patient_id}", headers=owner_headers)
    assert gone.status_code == 404

    still_findable = await api_client.get("/api/v1/patients?include_deleted=true&phone=%2B919999999911", headers=owner_headers)
    assert still_findable.json()["total"] == 1


# ---- Self-service (/me) --------------------------------------------------------


async def test_patient_can_view_their_own_linked_record(api_client: AsyncClient, test_clinic, owner_headers, login_as) -> None:
    created = await api_client.post(
        "/api/v1/patients", json={"first_name": "SelfService", "phone": "+919999999922"}, headers=owner_headers
    )
    patient_id = created.json()["patient"]["id"]

    patient_headers, patient_user_id = await login_as(role_code="PATIENT")
    # No API exists yet to link a patient record to a portal account
    # (that's the Patient Portal module) — link directly for this test.
    async with tenant_session(test_clinic.id) as session:
        await session.execute(update(Patient).where(Patient.id == patient_id).values(user_id=patient_user_id))

    response = await api_client.get("/api/v1/patients/me", headers=patient_headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "SelfService"


async def test_patient_without_a_linked_record_gets_404_on_me(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="PATIENT")
    response = await api_client.get("/api/v1/patients/me", headers=headers)
    assert response.status_code == 404
