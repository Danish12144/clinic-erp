"""Tenant-isolation suite for the Tenancy module — PRD-ARCHITECTURE.md §27:
"for every repository, a test that asserts a query scoped to Tenant A
never returns Tenant B's rows." Mirrors
tests/tenant_isolation/test_auth_tenant_isolation.py's approach: prove
isolation both through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop, not just app-layer filtering).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.tenancy.models import Branch, Clinic, TenantSetting

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"tenancy-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()

        user = User(tenant_id=clinic.id, role_id=role_map["OWNER"], email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()

        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug), user.id


async def _login(api_client: AsyncClient, clinic: Clinic, email: str, password: str) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/staff/login", json={"clinic_slug": clinic.slug, "identifier": email, "password": password}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def test_branch_created_in_one_tenant_is_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@tenancy-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@tenancy-b.clinic", "pw")

        created = await api_client.post("/api/v1/branches", json={"name": "Tenant A's Only Branch"}, headers=headers_a)
        branch_id = created.json()["id"]

        # Not in tenant B's list...
        list_b = await api_client.get("/api/v1/branches", headers=headers_b)
        assert all(b["id"] != branch_id for b in list_b.json())

        # ...and not directly fetchable by id from tenant B either (404,
        # not 403 — tenant B shouldn't even learn the id exists).
        direct_b = await api_client.get(f"/api/v1/branches/{branch_id}", headers=headers_b)
        assert direct_b.status_code == 404

        # But tenant A can see its own branch fine.
        direct_a = await api_client.get(f"/api/v1/branches/{branch_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_branch_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a = await _create_clinic_with_owner(role_map, email="owner@tenancy-c.clinic", password="pw")
    clinic_b, owner_b = await _create_clinic_with_owner(role_map, email="owner@tenancy-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            branch_a = Branch(tenant_id=clinic_a.id, name="A's Branch")
            session.add(branch_a)
            await session.flush()
            branch_a_id = branch_a.id

        async with tenant_session(clinic_b.id) as session:
            branch_b = Branch(tenant_id=clinic_b.id, name="B's Branch")
            session.add(branch_b)
            await session.flush()

        async with tenant_session(clinic_a.id) as session:
            # No `.where(Branch.tenant_id == ...)` at all — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(Branch))
            visible_ids = {b.id for b in result.scalars().all()}

        assert branch_a_id in visible_ids
        assert len(visible_ids) == 1
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_tenant_setting_isolation_via_api(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-e.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-f.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@tenancy-e.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@tenancy-f.clinic", "pw")

        await api_client.put(
            "/api/v1/clinics/me/settings/branding.primary_color", json={"value": "#ff0000"}, headers=headers_a
        )

        # Tenant B has never set this key — must be a clean 404, not
        # tenant A's value leaking through.
        response_b = await api_client.get("/api/v1/clinics/me/settings/branding.primary_color", headers=headers_b)
        assert response_b.status_code == 404

        response_a = await api_client.get("/api/v1/clinics/me/settings/branding.primary_color", headers=headers_a)
        assert response_a.status_code == 200
        assert response_a.json()["value"] == "#ff0000"
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_unscoped_tenant_setting_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-g.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-h.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            session.add(TenantSetting(tenant_id=clinic_a.id, key="defaults.consultation_fee", value=500))

        async with tenant_session(clinic_b.id) as session:
            session.add(TenantSetting(tenant_id=clinic_b.id, key="defaults.consultation_fee", value=999))

        async with tenant_session(clinic_a.id) as session:
            result = await session.execute(select(TenantSetting))
            rows = result.scalars().all()

        assert len(rows) == 1
        assert rows[0].tenant_id == clinic_a.id
        assert rows[0].value == 500
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_owner_of_one_tenant_cannot_edit_another_tenants_clinic_profile_by_guessing_endpoint(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    """`/clinics/me` always resolves to the caller's own tenant_id from
    their JWT — there's no way to target another clinic's profile, even
    as an Owner, since the endpoint takes no clinic id at all. Confirms
    that by checking tenant B's name is untouched after tenant A's Owner
    calls the (identically-shaped) update endpoint."""
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-i.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@tenancy-j.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@tenancy-i.clinic", "pw")
        await api_client.patch("/api/v1/clinics/me", json={"name": "Renamed By A"}, headers=headers_a)

        async with platform_admin_session() as session:
            result = await session.execute(select(Clinic).where(Clinic.id == clinic_b.id))
            refetched_b = result.scalar_one()
            assert refetched_b.name == "Isolation Test Clinic"
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
