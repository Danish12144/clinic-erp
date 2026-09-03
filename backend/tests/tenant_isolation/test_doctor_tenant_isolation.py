"""Tenant-isolation suite for the Doctor Management module —
PRD-ARCHITECTURE.md §27. Same approach as the Patient module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop), plus a check specific to this
module — an invite token from one tenant must not activate against
another tenant's clinic_slug.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.doctors.models import DoctorProfile
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"doctors-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_doctor_created_in_one_tenant_is_invisible_via_api_in_another(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@doctors-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@doctors-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@doctors-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@doctors-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/doctors", json={"first_name": "TenantA", "phone": "+919000044441"}, headers=headers_a
        )
        user_id = created.json()["doctor"]["user_id"]

        list_b = await api_client.get("/api/v1/doctors", headers=headers_b)
        assert all(d["user_id"] != user_id for d in list_b.json()["items"])

        direct_b = await api_client.get(f"/api/v1/doctors/{user_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/doctors/{user_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_doctor_profile_query(role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@doctors-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@doctors-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            doctor_a = User(tenant_id=clinic_a.id, role_id=role_map["DOCTOR"], phone="+919000044442")
            session.add(doctor_a)
            await session.flush()
            session.add(DoctorProfile(user_id=doctor_a.id, tenant_id=clinic_a.id))
            await session.flush()
            doctor_a_id = doctor_a.id

        async with tenant_session(clinic_b.id) as session:
            doctor_b = User(tenant_id=clinic_b.id, role_id=role_map["DOCTOR"], phone="+919000044443")
            session.add(doctor_b)
            await session.flush()
            session.add(DoctorProfile(user_id=doctor_b.id, tenant_id=clinic_b.id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(DoctorProfile.tenant_id == ...)` — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(DoctorProfile))
            visible_ids = {p.user_id for p in result.scalars().all()}

        assert visible_ids == {doctor_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_invite_token_from_one_tenant_does_not_activate_against_another_clinic_slug(
    api_client: AsyncClient, role_map: dict[str, uuid.UUID]
) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@doctors-e.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@doctors-f.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@doctors-e.clinic", "pw")

        created = await api_client.post(
            "/api/v1/doctors", json={"first_name": "CrossTenant", "phone": "+919000044444"}, headers=headers_a
        )
        token = created.json()["invite"]["debug_invite_token"]

        cross_attempt = await api_client.post(
            "/api/v1/doctors/accept-invite", json={"clinic_slug": clinic_b.slug, "token": token, "password": "password-123"}
        )
        assert cross_attempt.status_code == 400

        same_tenant_attempt = await api_client.post(
            "/api/v1/doctors/accept-invite", json={"clinic_slug": clinic_a.slug, "token": token, "password": "password-123"}
        )
        assert same_tenant_attempt.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
