"""Tenant-isolation suite for the Staff Management module —
PRD-ARCHITECTURE.md §27. Same approach as Doctor Management's suite: prove
isolation through the real HTTP API and through a deliberately unscoped
direct query (the RLS backstop). Cross-tenant invite-token rejection is
already covered generically by test_doctor_tenant_isolation.py against
the same shared Auth-module machinery — not repeated here.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.staff.models import StaffProfile
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"staff-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_staff_created_in_one_tenant_is_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@staff-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@staff-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@staff-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@staff-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/staff",
            json={"role_code": "NURSE", "first_name": "TenantA", "phone": "+919000055551"},
            headers=headers_a,
        )
        user_id = created.json()["staff"]["user_id"]

        list_b = await api_client.get("/api/v1/staff", headers=headers_b)
        assert all(s["user_id"] != user_id for s in list_b.json()["items"])

        direct_b = await api_client.get(f"/api/v1/staff/{user_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/staff/{user_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_staff_profile_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@staff-c.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@staff-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            staff_a = User(tenant_id=clinic_a.id, role_id=role_map["NURSE"], phone="+919000055552")
            session.add(staff_a)
            await session.flush()
            session.add(StaffProfile(user_id=staff_a.id, tenant_id=clinic_a.id))
            await session.flush()
            staff_a_id = staff_a.id

        async with tenant_session(clinic_b.id) as session:
            staff_b = User(tenant_id=clinic_b.id, role_id=role_map["NURSE"], phone="+919000055553")
            session.add(staff_b)
            await session.flush()
            session.add(StaffProfile(user_id=staff_b.id, tenant_id=clinic_b.id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(StaffProfile.tenant_id == ...)` — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(StaffProfile))
            visible_ids = {p.user_id for p in result.scalars().all()}

        assert visible_ids == {staff_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
