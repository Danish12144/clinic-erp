"""Tenant-isolation check for Financial Reports & Analytics —
PRD-ARCHITECTURE.md §27. This module has no tables of its own — it only
aggregates `invoices`/`invoice_line_items`/`payments`, whose own RLS
isolation is already proven by tests/tenant_isolation/
test_billing_tenant_isolation.py. This just checks the aggregation itself
doesn't leak a sibling tenant's totals into the API response.
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
    slug = f"reports-isolation-{uuid.uuid4().hex[:10]}"
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


async def _create_branch(api_client: AsyncClient, headers: dict[str, str]) -> str:
    response = await api_client.post("/api/v1/branches", json={"name": "Branch"}, headers=headers)
    return response.json()["id"]


async def _create_patient(api_client: AsyncClient, headers: dict[str, str], *, phone: str) -> str:
    created = await api_client.post("/api/v1/patients", json={"first_name": "Pat", "phone": phone}, headers=headers)
    return created.json()["patient"]["id"]


async def test_financial_totals_do_not_leak_across_tenants(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a = await _create_clinic_with_owner(role_map, email="owner@reports-a.clinic", password="pw")
    clinic_b = await _create_clinic_with_owner(role_map, email="owner@reports-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@reports-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@reports-b.clinic", "pw")

        branch_a = await _create_branch(api_client, headers_a)
        patient_a = await _create_patient(api_client, headers_a, phone="+919000399901")
        invoice_a = await api_client.post(
            "/api/v1/billing/invoices",
            json={"branch_id": branch_a, "patient_id": patient_a, "line_items": [{"source_type": "OTHER", "description": "x", "unit_price": 1234}]},
            headers=headers_a,
        )
        invoice_a_id = invoice_a.json()["id"]
        await api_client.post(f"/api/v1/billing/invoices/{invoice_a_id}/issue", headers=headers_a)
        await api_client.post("/api/v1/billing/payments", json={"invoice_id": invoice_a_id, "amount": 1234, "method": "CASH"}, headers=headers_a)

        # Tenant B has no billing activity at all.
        summary_b = await api_client.get("/api/v1/billing/summary", headers=headers_b)
        assert summary_b.status_code == 200
        assert summary_b.json()["total_collected"] == "0.00"
        assert summary_b.json()["total_bills_raised"] == 0

        summary_a = await api_client.get("/api/v1/billing/summary", headers=headers_a)
        assert summary_a.json()["total_collected"] == "1234.00"
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
