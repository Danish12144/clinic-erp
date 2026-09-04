"""Tenant-isolation suite for the Patient EMR Timeline & Medical Documents
module — PRD-ARCHITECTURE.md §27. Same approach as every other module's
suite: prove isolation through the real HTTP API and through a
deliberately unscoped direct query (the RLS backstop) against
`medical_documents`, the one new table this module owns.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.emr.models import MedicalDocument
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"emr-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_emr_data_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@emr-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@emr-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@emr-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@emr-b.clinic", "pw")

        patient_a_id = await _create_patient(api_client, headers_a, phone="+919000499901")
        uploaded = await api_client.post(
            f"/api/v1/patients/{patient_a_id}/documents", json={"document_type": "OTHER", "title": "x", "storage_key": "s3://bucket/x.pdf"}, headers=headers_a
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        # Tenant B's Owner can't even resolve patient A's id (RLS on
        # `patients` itself), so the EMR/documents routes 404 for it.
        timeline_b = await api_client.get(f"/api/v1/patients/{patient_a_id}/emr", headers=headers_b)
        assert timeline_b.status_code == 404
        document_b = await api_client.get(f"/api/v1/patients/{patient_a_id}/documents/{document_id}", headers=headers_b)
        assert document_b.status_code == 404

        timeline_a = await api_client.get(f"/api/v1/patients/{patient_a_id}/emr", headers=headers_a)
        assert timeline_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_medical_document_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@emr-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@emr-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-EMR-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            doc_a = MedicalDocument(
                tenant_id=clinic_a.id, patient_id=patient_a.id, document_type="OTHER", title="A", storage_key="s3://x", uploaded_by=owner_a_id
            )
            session.add(doc_a)
            await session.flush()
            doc_a_id = doc_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-EMR-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            session.add(
                MedicalDocument(tenant_id=clinic_b.id, patient_id=patient_b.id, document_type="OTHER", title="B", storage_key="s3://y", uploaded_by=owner_b_id)
            )

        async with tenant_session(clinic_a.id) as session:
            # No `.where(MedicalDocument.tenant_id == ...)` — the app-layer
            # mistake RLS exists to catch.
            result = await session.execute(select(MedicalDocument))
            visible_ids = {d.id for d in result.scalars().all()}

        assert visible_ids == {doc_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
