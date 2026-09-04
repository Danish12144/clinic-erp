"""Tenant-isolation suite for Clinic Expenses — PRD-ARCHITECTURE.md §27.
Same approach as every other module's suite: prove isolation through the
real HTTP API and through a deliberately unscoped direct query (the RLS
backstop).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.expenses.models import Expense
from app.modules.tenancy.models import Branch, Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"expenses-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_expense_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@expenses-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@expenses-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@expenses-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@expenses-b.clinic", "pw")

        branch_a = await api_client.post("/api/v1/branches", json={"name": "Branch A"}, headers=headers_a)
        branch_a_id = branch_a.json()["id"]

        created = await api_client.post(
            "/api/v1/expenses",
            json={"branch_id": branch_a_id, "category": "RENT", "amount": "1000.00", "payment_mode": "CASH"},
            headers=headers_a,
        )
        assert created.status_code == 201
        expense_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/expenses", headers=headers_b)
        assert all(e["id"] != expense_id for e in list_b.json()["items"])
        assert list_b.json()["total_amount"] == "0.00"

        direct_b = await api_client.get(f"/api/v1/expenses/{expense_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/expenses/{expense_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_expenses_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@expenses-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@expenses-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            branch_a = Branch(tenant_id=clinic_a.id, name="Branch A")
            session.add(branch_a)
            await session.flush()
            expense_a = Expense(
                tenant_id=clinic_a.id, branch_id=branch_a.id, category="RENT", amount=Decimal("1000.00"),
                expense_date=date.today(), payment_mode="CASH", recorded_by=owner_a_id,
            )
            session.add(expense_a)
            await session.flush()
            expense_a_id = expense_a.id

        async with tenant_session(clinic_b.id) as session:
            branch_b = Branch(tenant_id=clinic_b.id, name="Branch B")
            session.add(branch_b)
            await session.flush()
            session.add(Expense(
                tenant_id=clinic_b.id, branch_id=branch_b.id, category="SUPPLIES", amount=Decimal("500.00"),
                expense_date=date.today(), payment_mode="UPI", recorded_by=owner_b_id,
            ))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            result = await session.execute(select(Expense))
            visible_ids = {e.id for e in result.scalars().all()}

        assert visible_ids == {expense_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
