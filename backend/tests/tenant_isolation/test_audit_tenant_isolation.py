"""Tenant-isolation suite for the Audit Logging module —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop).
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.audit.models import AuditLog
from app.modules.auth.models import User
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"audit-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_audit_logs_created_in_one_tenant_are_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@audit-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@audit-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@audit-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@audit-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/patients", json={"first_name": "TenantA", "phone": "+919000088881"}, headers=headers_a
        )
        patient_id = created.json()["patient"]["id"]

        list_b = await api_client.get(f"/api/v1/audit-logs?entity_type=patient&entity_id={patient_id}", headers=headers_b)
        assert list_b.json()["total"] == 0

        list_a = await api_client.get(f"/api/v1/audit-logs?entity_type=patient&entity_id={patient_id}", headers=headers_a)
        assert list_a.json()["total"] >= 1
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_audit_log_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@audit-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@audit-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            log_a = AuditLog(
                tenant_id=clinic_a.id, actor_user_id=owner_a_id, actor_role="OWNER", action="test.action", entity_type="test", entity_id=None
            )
            session.add(log_a)
            await session.flush()
            log_a_id = log_a.id

        async with tenant_session(clinic_b.id) as session:
            session.add(
                AuditLog(
                    tenant_id=clinic_b.id, actor_user_id=owner_b_id, actor_role="OWNER", action="test.action", entity_type="test", entity_id=None
                )
            )

        async with tenant_session(clinic_a.id) as session:
            # No `.where(AuditLog.tenant_id == ...)` — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(AuditLog))
            visible_ids = {row.id for row in result.scalars().all()}

        assert visible_ids == {log_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_audit_log_is_append_only_at_the_db_level(role_map: dict[str, uuid.UUID]) -> None:
    """PRD §14: audit_logs is insert-only, enforced via
    prevent_update_delete() (migration 0007) — not just app convention."""
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@audit-e.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            log_a = AuditLog(
                tenant_id=clinic_a.id, actor_user_id=owner_a_id, actor_role="OWNER", action="test.action", entity_type="test", entity_id=None
            )
            session.add(log_a)
            await session.flush()
            log_a_id = log_a.id

        with pytest.raises(Exception):
            async with tenant_session(clinic_a.id) as session:
                await session.execute(text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": str(log_a_id)})
    finally:
        await _teardown([clinic_a.id])
