"""End-to-end tests of the Doctor Management module's HTTP surface,
against a real Postgres — see tests/conftest.py (skipped automatically if
unreachable).
"""

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], name: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": name}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


# ---- Create / invite --------------------------------------------------------


async def test_owner_can_create_a_doctor_and_gets_a_debug_invite_token(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/doctors",
        json={"first_name": "Rakesh", "last_name": "Kumar", "phone": "+919876500001", "specialization": "Cardiology"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["doctor"]["first_name"] == "Rakesh"
    assert body["doctor"]["status"] == "INVITED"
    assert body["invite"]["debug_invite_token"] is not None


async def test_doctor_cannot_create_a_doctor(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.post(
        "/api/v1/doctors", json={"first_name": "X", "phone": "+919876500002"}, headers=headers
    )
    assert response.status_code == 403


async def test_creating_with_a_duplicate_phone_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.post(
        "/api/v1/doctors", json={"first_name": "A", "phone": "+919876500010"}, headers=owner_headers
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v1/doctors", json={"first_name": "B", "phone": "+919876500010"}, headers=owner_headers
    )
    assert second.status_code == 409


async def test_create_validates_branch_ids_belong_to_tenant(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/doctors",
        json={"first_name": "A", "phone": "+919876500011", "branch_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_create_assigns_branches(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, "Main Branch")
    response = await api_client.post(
        "/api/v1/doctors",
        json={"first_name": "A", "phone": "+919876500012", "branch_ids": [branch_id]},
        headers=owner_headers,
    )
    assert response.status_code == 201
    assert response.json()["doctor"]["branch_ids"] == [branch_id]


# ---- Accept invite ------------------------------------------------------------


async def test_accepting_invite_activates_the_account_and_allows_login(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Neha", "email": "neha.doctor@test-clinic.example"}, headers=owner_headers
    )
    token = created.json()["invite"]["debug_invite_token"]

    accept = await api_client.post(
        "/api/v1/auth/accept-invite",
        json={"clinic_slug": test_clinic.slug, "token": token, "password": "new-password-123"},
    )
    assert accept.status_code == 200

    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "neha.doctor@test-clinic.example", "password": "new-password-123"},
    )
    assert login.status_code == 200


async def test_accepting_invite_twice_fails_the_second_time(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Once", "phone": "+919876500020"}, headers=owner_headers
    )
    token = created.json()["invite"]["debug_invite_token"]

    first = await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )
    assert first.status_code == 200

    second = await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-456"}
    )
    assert second.status_code == 400


async def test_accepting_invite_with_wrong_token_fails(api_client: AsyncClient, test_clinic: Clinic) -> None:
    response = await api_client.post(
        "/api/v1/auth/accept-invite",
        json={"clinic_slug": test_clinic.slug, "token": "not-a-real-token", "password": "password-123"},
    )
    assert response.status_code == 400


async def test_resend_invite_invalidates_the_old_token(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Resend", "phone": "+919876500021"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]
    old_token = created.json()["invite"]["debug_invite_token"]

    resend = await api_client.post(f"/api/v1/doctors/{user_id}/invite/resend", headers=owner_headers)
    assert resend.status_code == 200
    new_token = resend.json()["debug_invite_token"]
    assert new_token != old_token

    stale_attempt = await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": old_token, "password": "password-123"}
    )
    assert stale_attempt.status_code == 400

    fresh_attempt = await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": new_token, "password": "password-123"}
    )
    assert fresh_attempt.status_code == 200


async def test_resend_invite_on_an_already_active_doctor_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Active", "phone": "+919876500022"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )

    response = await api_client.post(f"/api/v1/doctors/{user_id}/invite/resend", headers=owner_headers)
    assert response.status_code == 409


# ---- Read / search ----------------------------------------------------------


async def test_get_doctor_by_id(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Kiran", "phone": "+919876500030"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    response = await api_client.get(f"/api/v1/doctors/{user_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "Kiran"


async def test_get_nonexistent_doctor_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/doctors/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_receptionist_cannot_list_or_view_doctors(api_client: AsyncClient, login_as) -> None:
    """PRD §3 matrix: "Doctor profile management" is Owner F / Doctor O
    (own) / everyone else –."""
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.get("/api/v1/doctors", headers=headers)
    assert response.status_code == 403


async def test_search_pagination(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    for i in range(3):
        await api_client.post(
            "/api/v1/doctors", json={"first_name": f"Bulk{i}", "phone": f"+9198765001{i:02d}"}, headers=owner_headers
        )

    response = await api_client.get("/api/v1/doctors?limit=2&offset=0", headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["total"] >= 3


# ---- Self-service (/me) --------------------------------------------------------


async def test_doctor_can_view_and_update_their_own_profile(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    # DOCTOR-role users created via make_staff_user (the login_as fixture)
    # have no doctor_profiles row — this module's own creation flow is the
    # only thing that creates one in production, so /me 404s here.
    missing = await api_client.get("/api/v1/doctors/me", headers=headers)
    assert missing.status_code == 404


async def test_doctor_cannot_view_another_doctors_profile(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Other", "phone": "+919876500040"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.get(f"/api/v1/doctors/{user_id}", headers=headers)
    assert response.status_code == 403


# ---- Update / lifecycle --------------------------------------------------------


async def test_owner_can_update_any_doctors_profile(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Anita", "phone": "+919876500050"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    updated = await api_client.patch(
        f"/api/v1/doctors/{user_id}", json={"specialization": "Dermatology"}, headers=owner_headers
    )
    assert updated.status_code == 200
    assert updated.json()["specialization"] == "Dermatology"


async def test_update_with_empty_body_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Vikram", "phone": "+919876500051"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    response = await api_client.patch(f"/api/v1/doctors/{user_id}", json={}, headers=owner_headers)
    assert response.status_code == 422


async def test_deactivate_then_reactivate_doctor(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Cycle", "email": "cycle.doctor@test-clinic.example"}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )

    deactivate = await api_client.post(f"/api/v1/doctors/{user_id}/deactivate", headers=owner_headers)
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "INACTIVE"

    blocked_login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "cycle.doctor@test-clinic.example", "password": "password-123"},
    )
    assert blocked_login.status_code == 403

    reactivate = await api_client.post(f"/api/v1/doctors/{user_id}/reactivate", headers=owner_headers)
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "ACTIVE"

    allowed_login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "cycle.doctor@test-clinic.example", "password": "password-123"},
    )
    assert allowed_login.status_code == 200


async def test_owner_can_replace_branch_assignments(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_a = await _create_branch(api_client, owner_headers, "Branch A")
    branch_b = await _create_branch(api_client, owner_headers, "Branch B")

    created = await api_client.post(
        "/api/v1/doctors", json={"first_name": "Multi", "phone": "+919876500060", "branch_ids": [branch_a]}, headers=owner_headers
    )
    user_id = created.json()["doctor"]["user_id"]

    response = await api_client.put(f"/api/v1/doctors/{user_id}/branches", json={"branch_ids": [branch_b]}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["branch_ids"] == [branch_b]
