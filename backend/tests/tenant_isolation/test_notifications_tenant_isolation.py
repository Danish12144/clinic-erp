"""Tenant-isolation suite for Notification Templates & Outbox Integration —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop) across `notification_templates`
and the relocated `communication_logs`.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.notifications.models import CommunicationLog, NotificationTemplate
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"notif-isolation-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Isolation Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()
        user = User(tenant_id=clinic.id, role_id=role_map["OWNER"], email=email, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
        return Clinic(id=clinic.id, name=clinic.name, slug=clinic.slug), user.id


async def _login(api_client: AsyncClient, clinic: Clinic, email: str, password: str) -> dict[str, str]:
    response = await api_client.post("/api/v1/auth/staff/login", json={"clinic_slug": clinic.slug, "identifier": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _teardown(clinic_ids: list[uuid.UUID]) -> None:
    async with platform_admin_session() as session:
        for clinic_id in clinic_ids:
            await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


async def test_template_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@notif-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@notif-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@notif-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@notif-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/notifications/templates",
            json={"template_key": "TENANT_A_KEY", "channel": "WHATSAPP", "body_text": "Hello"},
            headers=headers_a,
        )
        assert created.status_code == 201
        template_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/notifications/templates", headers=headers_b)
        assert all(t["id"] != template_id for t in list_b.json()["items"])

        cross_tenant_update = await api_client.patch(f"/api/v1/notifications/templates/{template_id}", json={"is_active": False}, headers=headers_b)
        assert cross_tenant_update.status_code == 404

        cross_tenant_preview = await api_client.post("/api/v1/notifications/send-preview", json={"template_id": template_id}, headers=headers_b)
        assert cross_tenant_preview.status_code == 404
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_notifications_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@notif-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@notif-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            template_a = NotificationTemplate(tenant_id=clinic_a.id, template_key="A_KEY", channel="WHATSAPP", body_text="Hi")
            session.add(template_a)
            await session.flush()
            log_a = CommunicationLog(tenant_id=clinic_a.id, channel="WHATSAPP", status="QUEUED", template_id=template_a.id, rendered_body="Hi")
            session.add(log_a)
            await session.flush()
            template_a_id, log_a_id = template_a.id, log_a.id

        async with tenant_session(clinic_b.id) as session:
            template_b = NotificationTemplate(tenant_id=clinic_b.id, template_key="B_KEY", channel="WHATSAPP", body_text="Hi")
            session.add(template_b)
            await session.flush()
            session.add(CommunicationLog(tenant_id=clinic_b.id, channel="WHATSAPP", status="QUEUED", template_id=template_b.id, rendered_body="Hi"))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            template_result = await session.execute(select(NotificationTemplate))
            visible_template_ids = {t.id for t in template_result.scalars().all()}
            log_result = await session.execute(select(CommunicationLog))
            visible_log_ids = {l.id for l in log_result.scalars().all()}

        assert visible_template_ids == {template_a_id}
        assert visible_log_ids == {log_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
