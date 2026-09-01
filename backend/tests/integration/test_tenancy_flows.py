"""End-to-end tests of the Tenancy module's HTTP surface (clinic profile,
tenant settings, branches), against a real Postgres — see
tests/conftest.py (skipped automatically if unreachable).
"""

import pytest
from httpx import AsyncClient

from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


# ---- Clinic profile ---------------------------------------------------------


async def test_any_authenticated_user_can_view_clinic_profile(
    api_client: AsyncClient, test_clinic: Clinic, login_as
) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.get("/api/v1/clinics/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == str(test_clinic.id)
    assert response.json()["slug"] == test_clinic.slug


async def test_viewing_clinic_profile_without_auth_is_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/clinics/me")
    assert response.status_code == 401


async def test_owner_can_update_clinic_profile(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch(
        "/api/v1/clinics/me",
        json={"name": "Apex Health PolyClinic", "timezone": "Asia/Kolkata", "gst_number": "27AAPFU0939F1ZV"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Apex Health PolyClinic"
    assert body["gst_number"] == "27AAPFU0939F1ZV"

    refetched = await api_client.get("/api/v1/clinics/me", headers=owner_headers)
    assert refetched.json()["name"] == "Apex Health PolyClinic"


async def test_non_owner_cannot_update_clinic_profile(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.patch("/api/v1/clinics/me", json={"name": "Hijacked Clinic"}, headers=headers)
    assert response.status_code == 403


async def test_update_with_invalid_timezone_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch(
        "/api/v1/clinics/me", json={"timezone": "Not/A_Real_Zone"}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_update_slug_field_is_ignored_not_erroring(
    api_client: AsyncClient, test_clinic: Clinic, owner_headers: dict[str, str]
) -> None:
    # `slug` isn't part of the update schema — extra fields are silently
    # dropped by default Pydantic behavior, not rejected. Confirms the
    # slug genuinely can't be changed through this endpoint.
    response = await api_client.patch(
        "/api/v1/clinics/me", json={"slug": "hijacked-slug", "name": "Still Fine"}, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["slug"] == test_clinic.slug


# ---- Clinic settings bag -----------------------------------------------------


async def test_owner_can_upsert_get_list_and_delete_a_setting(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    upserted = await api_client.put(
        "/api/v1/clinics/me/settings/branding.primary_color",
        json={"value": "#2563eb"},
        headers=owner_headers,
    )
    assert upserted.status_code == 200
    assert upserted.json()["value"] == "#2563eb"

    fetched = await api_client.get("/api/v1/clinics/me/settings/branding.primary_color", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["key"] == "branding.primary_color"

    listed = await api_client.get("/api/v1/clinics/me/settings", headers=owner_headers)
    assert listed.status_code == 200
    assert any(s["key"] == "branding.primary_color" for s in listed.json())

    deleted = await api_client.delete("/api/v1/clinics/me/settings/branding.primary_color", headers=owner_headers)
    assert deleted.status_code == 204

    gone = await api_client.get("/api/v1/clinics/me/settings/branding.primary_color", headers=owner_headers)
    assert gone.status_code == 404


async def test_upsert_overwrites_existing_value(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await api_client.put(
        "/api/v1/clinics/me/settings/defaults.consultation_fee", json={"value": 500}, headers=owner_headers
    )
    second = await api_client.put(
        "/api/v1/clinics/me/settings/defaults.consultation_fee", json={"value": 750}, headers=owner_headers
    )
    assert second.status_code == 200
    assert second.json()["value"] == 750


async def test_malformed_setting_key_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/clinics/me/settings/Not Valid Key", json={"value": 1}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_non_owner_cannot_manage_settings(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.put(
        "/api/v1/clinics/me/settings/branding.primary_color", json={"value": "#000000"}, headers=headers
    )
    assert response.status_code == 403


# ---- Branches -----------------------------------------------------------------


async def test_owner_can_create_and_fetch_a_branch(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/v1/branches",
        json={
            "name": "Downtown Branch",
            "address": "123 Main St",
            "phone": "+911234567890",
            "working_hours": {"mon": {"open": "09:00", "close": "18:00"}},
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    branch_id = created.json()["id"]
    assert created.json()["working_hours"]["mon"]["open"] == "09:00"

    fetched = await api_client.get(f"/api/v1/branches/{branch_id}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Downtown Branch"


async def test_any_authenticated_staff_can_list_branches(
    api_client: AsyncClient, owner_headers: dict[str, str], login_as
) -> None:
    await api_client.post("/api/v1/branches", json={"name": "Uptown Branch"}, headers=owner_headers)

    nurse_headers, _ = await login_as(role_code="NURSE")
    response = await api_client.get("/api/v1/branches", headers=nurse_headers)

    assert response.status_code == 200
    assert any(b["name"] == "Uptown Branch" for b in response.json())


async def test_non_owner_cannot_create_a_branch(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.post("/api/v1/branches", json={"name": "Rogue Branch"}, headers=headers)
    assert response.status_code == 403


async def test_duplicate_branch_name_in_same_tenant_is_rejected(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    first = await api_client.post("/api/v1/branches", json={"name": "Only One"}, headers=owner_headers)
    assert first.status_code == 201

    second = await api_client.post("/api/v1/branches", json={"name": "Only One"}, headers=owner_headers)
    assert second.status_code == 409


async def test_owner_can_update_and_deactivate_a_branch(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/branches", json={"name": "Branch To Edit"}, headers=owner_headers)
    branch_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/branches/{branch_id}", json={"phone": "+919999999999", "is_active": False}, headers=owner_headers
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+919999999999"
    assert updated.json()["is_active"] is False


async def test_updating_branch_name_to_an_existing_one_conflicts(
    api_client: AsyncClient, owner_headers: dict[str, str]
) -> None:
    await api_client.post("/api/v1/branches", json={"name": "Branch A"}, headers=owner_headers)
    created_b = await api_client.post("/api/v1/branches", json={"name": "Branch B"}, headers=owner_headers)
    branch_b_id = created_b.json()["id"]

    response = await api_client.patch(
        f"/api/v1/branches/{branch_b_id}", json={"name": "Branch A"}, headers=owner_headers
    )
    assert response.status_code == 409


async def test_getting_a_nonexistent_branch_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get(
        "/api/v1/branches/00000000-0000-0000-0000-000000000000", headers=owner_headers
    )
    assert response.status_code == 404


async def test_update_with_empty_body_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    created = await api_client.post("/api/v1/branches", json={"name": "Branch C"}, headers=owner_headers)
    branch_id = created.json()["id"]

    response = await api_client.patch(f"/api/v1/branches/{branch_id}", json={}, headers=owner_headers)
    assert response.status_code == 422
