"""End-to-end tests of the Clinic Letterhead Configuration HTTP surface
(config CRUD + resolve) against a real Postgres — see tests/conftest.py
(skipped automatically if unreachable).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_branch(api_client: AsyncClient, owner_headers: dict[str, str], *, address: str, phone: str) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "LetterheadBranch", "address": address, "phone": phone}, headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def test_get_config_returns_defaults_when_unset(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/letterhead/config", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["header_source"] == "AUTO"
    assert body["physical_top_margin_mm"] == 40.0


async def test_owner_can_update_config(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/letterhead/config",
        json={"header_source": "AUTO", "logo_url": "https://cdn.example.com/logo.png", "physical_top_margin_mm": 55, "physical_bottom_margin_mm": 15},
        headers=owner_headers,
    )
    assert response.status_code == 200

    refetched = await api_client.get("/api/v1/letterhead/config", headers=owner_headers)
    assert refetched.json()["logo_url"] == "https://cdn.example.com/logo.png"
    assert refetched.json()["physical_top_margin_mm"] == 55


async def test_non_owner_cannot_update_config(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="DOCTOR")
    response = await api_client.put("/api/v1/letterhead/config", json={"physical_top_margin_mm": 10}, headers=headers)
    assert response.status_code == 403


async def test_any_authenticated_role_can_read_config(api_client: AsyncClient, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST")
    response = await api_client.get("/api/v1/letterhead/config", headers=headers)
    assert response.status_code == 200


async def test_custom_asset_without_header_image_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put("/api/v1/letterhead/config", json={"header_source": "CUSTOM_ASSET"}, headers=owner_headers)
    assert response.status_code == 422


async def test_resolve_physical_mode_omits_header_and_footer(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await api_client.put("/api/v1/letterhead/config", json={"physical_top_margin_mm": 45, "physical_bottom_margin_mm": 25}, headers=owner_headers)

    response = await api_client.get("/api/v1/letterhead/resolve?mode=PHYSICAL", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["header"] is None
    assert body["footer"] is None
    assert body["top_margin_mm"] == 45
    assert body["bottom_margin_mm"] == 25


async def test_resolve_digital_auto_mode_composes_header_from_clinic_and_branch(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    branch_id = await _create_branch(api_client, owner_headers, address="221B Baker Street", phone="+919999911111")

    response = await api_client.get(f"/api/v1/letterhead/resolve?mode=DIGITAL&branch_id={branch_id}", headers=owner_headers)
    assert response.status_code == 200
    header = response.json()["header"]
    assert header["source"] == "AUTO"
    assert header["address"] == "221B Baker Street"
    assert header["contact"] == "+919999911111"


async def test_resolve_digital_custom_asset_mode_returns_image_urls(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    await api_client.put(
        "/api/v1/letterhead/config",
        json={"header_source": "CUSTOM_ASSET", "header_image_url": "https://cdn.example.com/h.png", "footer_image_url": "https://cdn.example.com/f.png"},
        headers=owner_headers,
    )

    response = await api_client.get("/api/v1/letterhead/resolve?mode=DIGITAL", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["source"] == "CUSTOM_ASSET"
    assert body["header"]["image_url"] == "https://cdn.example.com/h.png"
    assert body["footer"]["image_url"] == "https://cdn.example.com/f.png"


async def test_resolve_with_nonexistent_branch_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get(
        "/api/v1/letterhead/resolve?mode=DIGITAL&branch_id=00000000-0000-0000-0000-000000000000", headers=owner_headers
    )
    assert response.status_code == 422
