"""Tenant-isolation suite for Lead Pipeline / CRM Funnel —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop) across both new tables.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.leads.models import Lead, LeadInteraction
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"leads-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_lead_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@leads-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@leads-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@leads-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@leads-b.clinic", "pw")

        created = await api_client.post("/api/v1/leads", json={"first_name": "TenantALead", "phone": "+919000799901"}, headers=headers_a)
        assert created.status_code == 201
        lead_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/leads", headers=headers_b)
        assert all(l["id"] != lead_id for l in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/leads/{lead_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/leads/{lead_id}", headers=headers_a)
        assert direct_a.status_code == 200

        cross_tenant_interaction = await api_client.post(
            f"/api/v1/leads/{lead_id}/interactions", json={"interaction_type": "CALL"}, headers=headers_b
        )
        assert cross_tenant_interaction.status_code == 404

        cross_tenant_convert = await api_client.post(f"/api/v1/leads/{lead_id}/convert", json={}, headers=headers_b)
        assert cross_tenant_convert.status_code == 404
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_leads_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@leads-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@leads-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            lead_a = Lead(tenant_id=clinic_a.id, first_name="A")
            session.add(lead_a)
            await session.flush()
            interaction_a = LeadInteraction(tenant_id=clinic_a.id, lead_id=lead_a.id, interaction_type="NOTE", performed_by=owner_a_id)
            session.add(interaction_a)
            await session.flush()
            lead_a_id, interaction_a_id = lead_a.id, interaction_a.id

        async with tenant_session(clinic_b.id) as session:
            lead_b = Lead(tenant_id=clinic_b.id, first_name="B")
            session.add(lead_b)
            await session.flush()
            session.add(LeadInteraction(tenant_id=clinic_b.id, lead_id=lead_b.id, interaction_type="NOTE", performed_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            lead_result = await session.execute(select(Lead))
            visible_lead_ids = {l.id for l in lead_result.scalars().all()}
            interaction_result = await session.execute(select(LeadInteraction))
            visible_interaction_ids = {i.id for i in interaction_result.scalars().all()}

        assert visible_lead_ids == {lead_a_id}
        assert visible_interaction_ids == {interaction_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
