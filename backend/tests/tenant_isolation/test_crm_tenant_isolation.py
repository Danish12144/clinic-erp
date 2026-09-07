"""Tenant-isolation suite for CRM & Follow-ups — PRD-ARCHITECTURE.md §27.
Same approach as every other module's suite: prove isolation through the
real HTTP API and through a deliberately unscoped direct query (the RLS
backstop) across both new tables.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.crm.models import FollowUp
from app.modules.notifications.models import CommunicationLog
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"crm-isolation-{uuid.uuid4().hex[:10]}"
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


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_follow_up_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@crm-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@crm-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@crm-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@crm-b.clinic", "pw")

        patient_a = await _create_patient(api_client, headers_a, phone="+919000699901")
        due_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        created = await api_client.post("/api/v1/crm/follow-ups", json={"patient_id": patient_a, "due_at": due_at}, headers=headers_a)
        assert created.status_code == 201
        follow_up_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/crm/follow-ups", headers=headers_b)
        assert all(f["id"] != follow_up_id for f in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/crm/follow-ups/{follow_up_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/crm/follow-ups/{follow_up_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_crm_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@crm-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@crm-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-CRM-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            log_a = CommunicationLog(tenant_id=clinic_a.id, patient_id=patient_a.id, channel="WHATSAPP", status="QUEUED")
            session.add(log_a)
            await session.flush()
            follow_up_a = FollowUp(tenant_id=clinic_a.id, patient_id=patient_a.id, due_at=datetime.now(timezone.utc), reminder_log_id=log_a.id, created_by=owner_a_id)
            session.add(follow_up_a)
            await session.flush()
            log_a_id, follow_up_a_id = log_a.id, follow_up_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-CRM-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            log_b = CommunicationLog(tenant_id=clinic_b.id, patient_id=patient_b.id, channel="WHATSAPP", status="QUEUED")
            session.add(log_b)
            await session.flush()
            session.add(FollowUp(tenant_id=clinic_b.id, patient_id=patient_b.id, due_at=datetime.now(timezone.utc), reminder_log_id=log_b.id, created_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            follow_up_result = await session.execute(select(FollowUp))
            visible_follow_up_ids = {f.id for f in follow_up_result.scalars().all()}
            log_result = await session.execute(select(CommunicationLog))
            visible_log_ids = {l.id for l in log_result.scalars().all()}

        assert visible_follow_up_ids == {follow_up_a_id}
        assert visible_log_ids == {log_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
