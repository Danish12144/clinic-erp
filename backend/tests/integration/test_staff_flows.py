"""End-to-end tests of the Staff Management module's HTTP surface, against
a real Postgres — see tests/conftest.py (skipped automatically if
unreachable).

The invite/accept-token mechanism itself (cross-tenant token rejection,
double-accept, resend invalidating the old token) is already thoroughly
covered by tests/integration/test_doctor_flows.py against the same shared
Auth-module machinery — not re-tested exhaustively here, just confirmed
to work end-to-end once for a non-doctor role.
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


async def test_owner_can_create_staff_and_gets_a_debug_invite_token(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/staff",
        json={"role_code": "RECEPTIONIST", "first_name": "Priya", "phone": "+919876600001", "designation": "Front Desk"},
        headers=owner_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["staff"]["role_code"] == "RECEPTIONIST"
    assert body["staff"]["status"] == "INVITED"
    assert body["invite"]["debug_invite_token"] is not None


async def test_receptionist_cannot_create_staff(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "X", "phone": "+919876600002"}, headers=headers
    )
    assert response.status_code == 403


async def test_creating_with_a_duplicate_phone_conflicts(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "A", "phone": "+919876600010"}, headers=owner_headers
    )
    assert first.status_code == 201

    second = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "B", "phone": "+919876600010"}, headers=owner_headers
    )
    assert second.status_code == 409


async def test_create_validates_branch_ids_belong_to_tenant(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/staff",
        json={
            "role_code": "NURSE",
            "first_name": "A",
            "phone": "+919876600011",
            "branch_ids": ["00000000-0000-0000-0000-000000000000"],
        },
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_create_rejects_a_non_staff_role_code(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post(
        "/api/v1/staff", json={"role_code": "DOCTOR", "first_name": "A", "phone": "+919876600012"}, headers=owner_headers
    )
    assert response.status_code == 422


# ---- Accept invite (shared Auth-module machinery) ------------------------------


async def test_accepting_invite_activates_the_account_and_allows_login(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/staff",
        json={"role_code": "PHARMACY_STAFF", "first_name": "Neha", "email": "neha.staff@test-clinic.example"},
        headers=owner_headers,
    )
    token = created.json()["invite"]["debug_invite_token"]

    accept = await api_client.post(
        "/api/v1/auth/accept-invite",
        json={"clinic_slug": test_clinic.slug, "token": token, "password": "new-password-123"},
    )
    assert accept.status_code == 200

    login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "neha.staff@test-clinic.example", "password": "new-password-123"},
    )
    assert login.status_code == 200


# ---- Read / search ----------------------------------------------------------


async def test_get_staff_by_id(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/staff", json={"role_code": "LAB_STAFF", "first_name": "Kiran", "phone": "+919876600030"}, headers=owner_headers
    )
    user_id = created.json()["staff"]["user_id"]

    response = await api_client.get(f"/api/v1/staff/{user_id}", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["first_name"] == "Kiran"
    assert response.json()["role_code"] == "LAB_STAFF"


async def test_get_nonexistent_staff_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/staff/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_doctor_cannot_list_or_view_staff(api_client: AsyncClient, login_as) -> None:
    """PRD §3 matrix: "Staff, roles & permissions" is Owner F / everyone
    else – (unlike Doctor Management, not even an "own record" carve-out)."""
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.get("/api/v1/staff", headers=headers)
    assert response.status_code == 403


async def test_search_filters_by_role_code(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "NurseOne", "phone": "+919876600040"}, headers=owner_headers
    )
    await api_client.post(
        "/api/v1/staff",
        json={"role_code": "RECEPTIONIST", "first_name": "RecepOne", "phone": "+919876600041"},
        headers=owner_headers,
    )

    response = await api_client.get("/api/v1/staff?role_code=NURSE", headers=owner_headers)
    assert response.status_code == 200
    assert all(s["role_code"] == "NURSE" for s in response.json()["items"])
    assert any(s["first_name"] == "NurseOne" for s in response.json()["items"])


async def test_search_pagination(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    for i in range(3):
        await api_client.post(
            "/api/v1/staff",
            json={"role_code": "OTHER_STAFF", "first_name": f"Bulk{i}", "phone": f"+9198766001{i:02d}"},
            headers=owner_headers,
        )

    response = await api_client.get("/api/v1/staff?limit=2&offset=0", headers=owner_headers)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["total"] >= 3


# ---- Update / lifecycle --------------------------------------------------------


async def test_owner_can_update_a_staff_members_profile(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "Anita", "phone": "+919876600050"}, headers=owner_headers
    )
    user_id = created.json()["staff"]["user_id"]

    updated = await api_client.patch(
        f"/api/v1/staff/{user_id}", json={"designation": "Senior Nurse", "employee_code": "EMP-001"}, headers=owner_headers
    )
    assert updated.status_code == 200
    assert updated.json()["designation"] == "Senior Nurse"
    assert updated.json()["employee_code"] == "EMP-001"


async def test_update_with_empty_body_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/staff", json={"role_code": "NURSE", "first_name": "Vikram", "phone": "+919876600051"}, headers=owner_headers
    )
    user_id = created.json()["staff"]["user_id"]

    response = await api_client.patch(f"/api/v1/staff/{user_id}", json={}, headers=owner_headers)
    assert response.status_code == 422


async def test_deactivate_then_reactivate_staff(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/staff",
        json={"role_code": "RECEPTIONIST", "first_name": "Cycle", "email": "cycle.staff@test-clinic.example"},
        headers=owner_headers,
    )
    user_id = created.json()["staff"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )

    deactivate = await api_client.post(f"/api/v1/staff/{user_id}/deactivate", headers=owner_headers)
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "INACTIVE"

    blocked_login = await api_client.post(
        "/api/v1/auth/staff/login",
        json={"clinic_slug": test_clinic.slug, "identifier": "cycle.staff@test-clinic.example", "password": "password-123"},
    )
    assert blocked_login.status_code == 403

    reactivate = await api_client.post(f"/api/v1/staff/{user_id}/reactivate", headers=owner_headers)
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "ACTIVE"


async def test_owner_can_replace_branch_assignments(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_a = await _create_branch(api_client, owner_headers, "Staff Branch A")
    branch_b = await _create_branch(api_client, owner_headers, "Staff Branch B")

    created = await api_client.post(
        "/api/v1/staff",
        json={"role_code": "NURSE", "first_name": "Multi", "phone": "+919876600060", "branch_ids": [branch_a]},
        headers=owner_headers,
    )
    user_id = created.json()["staff"]["user_id"]

    response = await api_client.put(f"/api/v1/staff/{user_id}/branches", json={"branch_ids": [branch_b]}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["branch_ids"] == [branch_b]


async def test_resend_invite_on_an_already_active_staff_member_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic: Clinic
) -> None:
    created = await api_client.post(
        "/api/v1/staff",
        json={"role_code": "OTHER_STAFF", "first_name": "Active", "phone": "+919876600070"},
        headers=owner_headers,
    )
    user_id = created.json()["staff"]["user_id"]
    token = created.json()["invite"]["debug_invite_token"]
    await api_client.post(
        "/api/v1/auth/accept-invite", json={"clinic_slug": test_clinic.slug, "token": token, "password": "password-123"}
    )

    response = await api_client.post(f"/api/v1/staff/{user_id}/invite/resend", headers=owner_headers)
    assert response.status_code == 409
