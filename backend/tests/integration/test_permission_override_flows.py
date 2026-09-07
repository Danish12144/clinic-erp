"""End-to-end tests of the Permission Override write endpoint —
PRD-ARCHITECTURE.md §13's write side (§3's own flagship example: an Owner
enabling `vitals.record` for Receptionists at their clinic without a code
change), against a real Postgres. See tests/conftest.py (skipped
automatically if unreachable).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


async def _login(api_client: AsyncClient, test_clinic, identifier: str, password: str) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/staff/login", json={"clinic_slug": test_clinic.slug, "identifier": identifier, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---- The flagship PRD §3/§13 round trip -----------------------------------------


async def test_owner_can_grant_a_role_level_override_and_it_takes_effect_on_next_login(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic, login_as
) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST", email="recep-override@apex.clinic")
    before = await api_client.get("/api/v1/auth/me", headers=headers)
    assert "vitals.record" not in before.json()["permissions"]

    response = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "RECEPTIONIST", "permission_code": "vitals.record", "granted": True}, headers=owner_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role_code"] == "RECEPTIONIST"
    assert body["permission_code"] == "vitals.record"
    assert body["granted"] is True

    relogged_in = await _login(api_client, test_clinic, "recep-override@apex.clinic", "correct-horse-battery-staple")
    after = await api_client.get("/api/v1/auth/me", headers=relogged_in)
    assert "vitals.record" in after.json()["permissions"]


async def test_setting_the_same_override_twice_updates_rather_than_duplicates(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    first = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "DOCTOR", "permission_code": "expenses.manage", "granted": True}, headers=owner_headers
    )
    assert first.status_code == 200
    override_id = first.json()["id"]

    second = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "DOCTOR", "permission_code": "expenses.manage", "granted": False}, headers=owner_headers
    )
    assert second.status_code == 200
    assert second.json()["id"] == override_id
    assert second.json()["granted"] is False

    listed = await api_client.get("/api/v1/permission-overrides?role_code=DOCTOR", headers=owner_headers)
    matches = [o for o in listed.json()["items"] if o["permission_code"] == "expenses.manage"]
    assert len(matches) == 1
    assert matches[0]["granted"] is False


async def test_user_level_override_revokes_a_default_on_permission_for_one_user_only(
    api_client: AsyncClient, owner_headers: dict[str, str], test_clinic, login_as
) -> None:
    headers_a, user_id_a = await login_as(role_code="NURSE", email="nurse-a@apex.clinic")
    headers_b, _ = await login_as(role_code="NURSE", email="nurse-b@apex.clinic")

    before_a = await api_client.get("/api/v1/auth/me", headers=headers_a)
    assert "vitals.record" in before_a.json()["permissions"]  # Nurse defaults to on

    response = await api_client.put(
        "/api/v1/permission-overrides", json={"user_id": str(user_id_a), "permission_code": "vitals.record", "granted": False}, headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == str(user_id_a)

    relogged_a = await _login(api_client, test_clinic, "nurse-a@apex.clinic", "correct-horse-battery-staple")
    after_a = await api_client.get("/api/v1/auth/me", headers=relogged_a)
    assert "vitals.record" not in after_a.json()["permissions"]

    still_b = await api_client.get("/api/v1/auth/me", headers=headers_b)
    assert "vitals.record" in still_b.json()["permissions"]  # unaffected


async def test_deleting_an_override_reverts_to_the_role_default(api_client: AsyncClient, owner_headers: dict[str, str], test_clinic, login_as) -> None:
    headers, _ = await login_as(role_code="RECEPTIONIST", email="recep-revert@apex.clinic")
    grant = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "RECEPTIONIST", "permission_code": "vitals.record", "granted": True}, headers=owner_headers
    )
    override_id = grant.json()["id"]

    granted_login = await _login(api_client, test_clinic, "recep-revert@apex.clinic", "correct-horse-battery-staple")
    assert "vitals.record" in (await api_client.get("/api/v1/auth/me", headers=granted_login)).json()["permissions"]

    deleted = await api_client.delete(f"/api/v1/permission-overrides/{override_id}", headers=owner_headers)
    assert deleted.status_code == 204

    reverted_login = await _login(api_client, test_clinic, "recep-revert@apex.clinic", "correct-horse-battery-staple")
    assert "vitals.record" not in (await api_client.get("/api/v1/auth/me", headers=reverted_login)).json()["permissions"]


# ---- Validation -------------------------------------------------------------------


async def test_providing_both_role_code_and_user_id_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    _, user_id = await login_as(role_code="NURSE", email="both-targets@apex.clinic")
    response = await api_client.put(
        "/api/v1/permission-overrides",
        json={"role_code": "NURSE", "user_id": str(user_id), "permission_code": "vitals.record", "granted": True},
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_providing_neither_role_code_nor_user_id_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/permission-overrides", json={"permission_code": "vitals.record", "granted": True}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_unknown_role_code_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "SUPERADMIN", "permission_code": "vitals.record", "granted": True}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_unknown_permission_code_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "NURSE", "permission_code": "not.a.real.permission", "granted": True}, headers=owner_headers
    )
    assert response.status_code == 422


async def test_unknown_user_id_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.put(
        "/api/v1/permission-overrides",
        json={"user_id": "00000000-0000-0000-0000-000000000000", "permission_code": "vitals.record", "granted": True},
        headers=owner_headers,
    )
    assert response.status_code == 422


async def test_deleting_a_nonexistent_override_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.delete("/api/v1/permission-overrides/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


# ---- RBAC ---------------------------------------------------------------------------


async def test_non_owner_roles_cannot_manage_permission_overrides(api_client: AsyncClient, login_as) -> None:
    for role in ("RECEPTIONIST", "DOCTOR", "NURSE"):
        headers, _ = await login_as(role_code=role)
        write = await api_client.put(
            "/api/v1/permission-overrides", json={"role_code": "NURSE", "permission_code": "vitals.record", "granted": True}, headers=headers
        )
        assert write.status_code == 403, role
        read = await api_client.get("/api/v1/permission-overrides", headers=headers)
        assert read.status_code == 403, role


# ---- Audit trail ----------------------------------------------------------------------


async def test_permission_override_changes_are_audited(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    set_response = await api_client.put(
        "/api/v1/permission-overrides", json={"role_code": "RECEPTIONIST", "permission_code": "vitals.record", "granted": True}, headers=owner_headers
    )
    override_id = set_response.json()["id"]
    await api_client.delete(f"/api/v1/permission-overrides/{override_id}", headers=owner_headers)

    logs = await api_client.get("/api/v1/audit-logs", headers=owner_headers)
    actions = {entry["action"] for entry in logs.json()["items"] if entry["entity_id"] == override_id}
    assert {"permission_override.set", "permission_override.delete"} <= actions
