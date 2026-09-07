"""Tenant-isolation suite for File Storage & Uploads —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop). Storage keys are namespaced by
tenant_id (see app/modules/files/service.py), so even the on-disk file
paths never collide across tenants — verified here at the `documents`
registry level, which is what actually gates access.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.files.models import Document
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"files-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_document_uploaded_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@files-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@files-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@files-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@files-b.clinic", "pw")

        uploaded = await api_client.post(
            "/api/v1/files/upload",
            data={"owner_type": "LETTERHEAD_ASSET", "owner_id": str(clinic_a.id)},
            files={"file": ("logo.png", b"tenant-a-bytes", "image/png")},
            headers=headers_a,
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        cross_tenant_meta = await api_client.get(f"/api/v1/files/{document_id}", headers=headers_b)
        assert cross_tenant_meta.status_code == 404
        cross_tenant_content = await api_client.get(f"/api/v1/files/{document_id}/content", headers=headers_b)
        assert cross_tenant_content.status_code == 404

        own_meta = await api_client.get(f"/api/v1/files/{document_id}", headers=headers_a)
        assert own_meta.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_documents_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@files-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@files-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            doc_a = Document(
                tenant_id=clinic_a.id, owner_type="LETTERHEAD_ASSET", owner_id=clinic_a.id, storage_key="a/key.png",
                original_filename="a.png", uploaded_by=owner_a_id,
            )
            session.add(doc_a)
            await session.flush()
            doc_a_id = doc_a.id

        async with tenant_session(clinic_b.id) as session:
            session.add(Document(
                tenant_id=clinic_b.id, owner_type="LETTERHEAD_ASSET", owner_id=clinic_b.id, storage_key="b/key.png",
                original_filename="b.png", uploaded_by=owner_b_id,
            ))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            result = await session.execute(select(Document))
            visible_ids = {d.id for d in result.scalars().all()}

        assert visible_ids == {doc_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
