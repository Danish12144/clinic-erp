"""The dedicated tenant-isolation suite required by PRD-ARCHITECTURE.md
§27: "for every repository, a test that asserts a query scoped to Tenant A
never returns Tenant B's rows... the single highest-priority test category
given the 'strong separation between tenants' mandate."

These tests specifically probe the Row-Level Security backstop (§11) —
not just the application-layer tenant_id filters repository methods
already apply. The key test, `test_rls_blocks_even_a_deliberately_unscoped_query`,
issues a query with NO tenant_id WHERE clause at all and proves Postgres
itself still won't return another tenant's rows.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import Permission, PermissionOverride, User
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"tenant-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()

        user = User(
            tenant_id=clinic.id,
            role_id=role_map["OWNER"],
            email=email,
            password_hash=hash_password(password),
        )
        session.add(user)
        await session.flush()

        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug), user.id


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def test_rls_blocks_even_a_deliberately_unscoped_query(role_map: dict[str, uuid.UUID]) -> None:
    """The core guarantee: even a query that FORGOT to filter by tenant_id
    (simulating an app-layer bug) must not return another tenant's rows,
    because Postgres RLS enforces it independently."""
    clinic_a, user_a_id = await _create_clinic_with_owner(role_map, email="owner@tenant-a.clinic", password="pw")
    clinic_b, user_b_id = await _create_clinic_with_owner(role_map, email="owner@tenant-b.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            # Deliberately no `.where(User.tenant_id == ...)` — this is
            # exactly the app-layer mistake RLS exists to catch.
            result = await session.execute(select(User))
            visible_user_ids = {u.id for u in result.scalars().all()}

        assert user_a_id in visible_user_ids
        assert user_b_id not in visible_user_ids
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_direct_lookup_by_id_across_tenants(role_map: dict[str, uuid.UUID]) -> None:
    """Even a targeted `WHERE id = :known_id` lookup must fail if the
    session's tenant context doesn't match — proves RLS, not just the
    app's habit of adding a tenant_id filter, is what's enforcing this."""
    clinic_a, user_a_id = await _create_clinic_with_owner(role_map, email="owner@tenant-c.clinic", password="pw")
    clinic_b, user_b_id = await _create_clinic_with_owner(role_map, email="owner@tenant-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            result = await session.execute(select(User).where(User.id == user_b_id))
            assert result.scalar_one_or_none() is None

            result = await session.execute(select(User).where(User.id == user_a_id))
            assert result.scalar_one_or_none() is not None
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_clinic_row_itself_is_isolated(role_map: dict[str, uuid.UUID]) -> None:
    """clinics is the tenant root and gets a special-cased RLS policy
    (`id = tenant_id`, not `tenant_id = tenant_id`) — worth its own test."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-e.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-f.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            result = await session.execute(select(Clinic))
            visible_ids = {c.id for c in result.scalars().all()}

        assert visible_ids == {clinic_a.id}
        assert clinic_b.id not in visible_ids
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_login_with_correct_credentials_but_wrong_tenant_slug_fails(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    """A real end-to-end case: a user's actual email+password, submitted
    against a *different* clinic's slug, must be rejected — proves the
    login flow can't be tricked into cross-tenant authentication even with
    valid credentials for some tenant."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="shared-looking-email@clinic.com", password="pw-a")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-g.clinic", password="pw-b")

    try:
        response = await api_client.post(
            "/api/v1/auth/staff/login",
            json={
                "clinic_slug": clinic_b.slug,  # tenant B's slug...
                "identifier": "shared-looking-email@clinic.com",  # ...with tenant A's user
                "password": "pw-a",
            },
        )
        assert response.status_code == 401
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_permission_override_in_one_tenant_does_not_leak_to_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    """A clinic-specific RBAC customization (PRD §13) must stay scoped to
    that clinic — enabling vitals.record for Receptionists at Clinic A
    must not grant it at Clinic B."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-h.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-i.clinic", password="pw")

    async with platform_admin_session() as session:
        receptionist_a = User(
            tenant_id=clinic_a.id, role_id=role_map["RECEPTIONIST"], email="front-desk@tenant-h.clinic",
            password_hash=hash_password("pw"),
        )
        receptionist_b = User(
            tenant_id=clinic_b.id, role_id=role_map["RECEPTIONIST"], email="front-desk@tenant-i.clinic",
            password_hash=hash_password("pw"),
        )
        session.add_all([receptionist_a, receptionist_b])
        await session.flush()

        permission = (
            await session.execute(select(Permission).where(Permission.code == "vitals.record"))
        ).scalar_one()
        session.add(
            PermissionOverride(tenant_id=clinic_a.id, role_id=role_map["RECEPTIONIST"], permission_id=permission.id, granted=True)
        )

    try:
        login_a = await api_client.post(
            "/api/v1/auth/staff/login",
            json={"clinic_slug": clinic_a.slug, "identifier": "front-desk@tenant-h.clinic", "password": "pw"},
        )
        login_b = await api_client.post(
            "/api/v1/auth/staff/login",
            json={"clinic_slug": clinic_b.slug, "identifier": "front-desk@tenant-i.clinic", "password": "pw"},
        )

        me_a = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {login_a.json()['access_token']}"}
        )
        me_b = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {login_b.json()['access_token']}"}
        )

        assert "vitals.record" in set(me_a.json()["permissions"])
        assert "vitals.record" not in set(me_b.json()["permissions"])
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_permission_override_write_endpoint_is_tenant_isolated(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    """The new write side (migration-free — `permission_overrides` already
    existed; this is `PUT/GET/DELETE /api/v1/permission-overrides`) must
    respect tenant boundaries exactly like every other endpoint: Owner A
    can't see or delete Owner B's overrides, even by guessing an id."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-j.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenant-k.clinic", password="pw")

    try:
        login_a = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": clinic_a.slug, "identifier": "owner@tenant-j.clinic", "password": "pw"})
        login_b = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": clinic_b.slug, "identifier": "owner@tenant-k.clinic", "password": "pw"})
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

        created = await api_client.put(
            "/api/v1/permission-overrides", json={"role_code": "RECEPTIONIST", "permission_code": "vitals.record", "granted": True}, headers=headers_a
        )
        assert created.status_code == 200
        override_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/permission-overrides", headers=headers_b)
        assert all(o["id"] != override_id for o in list_b.json()["items"])

        cross_tenant_delete = await api_client.delete(f"/api/v1/permission-overrides/{override_id}", headers=headers_b)
        assert cross_tenant_delete.status_code == 404

        still_there = await api_client.get("/api/v1/permission-overrides", headers=headers_a)
        assert any(o["id"] == override_id for o in still_there.json()["items"])
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
