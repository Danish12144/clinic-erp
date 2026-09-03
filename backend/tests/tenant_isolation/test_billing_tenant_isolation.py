"""Tenant-isolation suite for Billing, Invoices & Payments —
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
from app.modules.auth.models import User
from app.modules.billing.models import Invoice, Payment
from app.modules.patients.models import Patient
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"billing-isolation-{uuid.uuid4().hex[:10]}"
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


async def _create_branch(api_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "Branch"}, headers=headers)
    return response.json()["id"]


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_invoice_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@billing-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@billing-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@billing-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@billing-b.clinic", "pw")

        branch_id = await _create_branch(api_client, headers_a)
        patient_id = await _create_patient(api_client, headers_a, phone="+919000299901")

        created = await api_client.post(
            "/api/v1/billing/invoices",
            json={"branch_id": branch_id, "patient_id": patient_id, "line_items": [{"source_type": "OTHER", "description": "x", "unit_price": 100}]},
            headers=headers_a,
        )
        assert created.status_code == 201
        invoice_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/billing/invoices", headers=headers_b)
        assert all(i["id"] != invoice_id for i in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_invoice_and_payment_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@billing-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@billing-d.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@billing-c.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@billing-d.clinic", "pw")
        branch_a_id = await _create_branch(api_client, headers_a)
        branch_b_id = await _create_branch(api_client, headers_b)

        async with tenant_session(clinic_a.id) as session:
            patient_a = Patient(tenant_id=clinic_a.id, mrn="MRN-BILL-A", first_name="A")
            session.add(patient_a)
            await session.flush()
            invoice_a = Invoice(tenant_id=clinic_a.id, branch_id=uuid.UUID(branch_a_id), patient_id=patient_a.id)
            session.add(invoice_a)
            await session.flush()
            payment_a = Payment(tenant_id=clinic_a.id, invoice_id=invoice_a.id, amount=100, method="CASH", recorded_by=owner_a_id)
            session.add(payment_a)
            await session.flush()
            invoice_a_id = invoice_a.id
            payment_a_id = payment_a.id

        async with tenant_session(clinic_b.id) as session:
            patient_b = Patient(tenant_id=clinic_b.id, mrn="MRN-BILL-B", first_name="B")
            session.add(patient_b)
            await session.flush()
            invoice_b = Invoice(tenant_id=clinic_b.id, branch_id=uuid.UUID(branch_b_id), patient_id=patient_b.id)
            session.add(invoice_b)
            await session.flush()
            session.add(Payment(tenant_id=clinic_b.id, invoice_id=invoice_b.id, amount=100, method="CASH", recorded_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            invoice_result = await session.execute(select(Invoice))
            visible_invoice_ids = {i.id for i in invoice_result.scalars().all()}
            payment_result = await session.execute(select(Payment))
            visible_payment_ids = {p.id for p in payment_result.scalars().all()}

        assert visible_invoice_ids == {invoice_a_id}
        assert visible_payment_ids == {payment_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
