"""Tenant-isolation check for Clinic Letterhead Configuration —
PRD-ARCHITECTURE.md §27. Thin by design: the config is stored as a
`TenantSetting` value, whose own isolation is already proven by
tests/tenant_isolation/test_tenancy_tenant_isolation.py — this just checks
the letterhead-specific read path (defaults-on-unset) doesn't leak a
sibling tenant's configured value.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.db import platform_admin_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> Clinic:
    slug = f"letterhead-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()
        user = User(tenant_id=clinic.id, role_id=role_map["OWNER"], email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug)


async def _login(api_client: AsyncClient, clinic: Clinic, email: str, password: str) -> dict[str, str]:
    response = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": clinic.slug, "identifier": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def test_letterhead_config_set_in_one_tenant_does_not_leak_into_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a = await _create_clinic_with_owner(role_map, email="owner@letterhead-a.clinic", password="pw")
    clinic_b = await _create_clinic_with_owner(role_map, email="owner@letterhead-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@letterhead-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@letterhead-b.clinic", "pw")

        await api_client.put("/api/v1/letterhead/config", json={"logo_url": "https://cdn.example.com/tenant-a-logo.png"}, headers=headers_a)

        config_b = await api_client.get("/api/v1/letterhead/config", headers=headers_b)
        assert config_b.status_code == 200
        assert config_b.json()["logo_url"] is None
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
