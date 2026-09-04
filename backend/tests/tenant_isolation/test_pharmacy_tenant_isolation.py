"""Tenant-isolation suite for Pharmacy & Inventory Management —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop) across all three new tables.
"""

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.pharmacy.models import Medicine, MedicineBatch, PharmacyInventoryTransaction
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"pharmacy-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_medicine_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@pharmacy-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@pharmacy-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@pharmacy-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@pharmacy-b.clinic", "pw")

        created = await api_client.post("/api/v1/pharmacy/medicines", json={"name": "TenantAMedicine"}, headers=headers_a)
        assert created.status_code == 201
        medicine_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/pharmacy/medicines", headers=headers_b)
        assert all(m["id"] != medicine_id for m in list_b.json()["items"])
        direct_b = await api_client.get(f"/api/v1/pharmacy/medicines/{medicine_id}", headers=headers_b)
        assert direct_b.status_code == 404
        direct_a = await api_client.get(f"/api/v1/pharmacy/medicines/{medicine_id}", headers=headers_a)
        assert direct_a.status_code == 200
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_pharmacy_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@pharmacy-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@pharmacy-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            medicine_a = Medicine(tenant_id=clinic_a.id, name="A")
            session.add(medicine_a)
            await session.flush()
            batch_a = MedicineBatch(tenant_id=clinic_a.id, medicine_id=medicine_a.id, batch_number="B1", expiry_date=date.today() + timedelta(days=30), quantity_on_hand=10)
            session.add(batch_a)
            await session.flush()
            txn_a = PharmacyInventoryTransaction(tenant_id=clinic_a.id, batch_id=batch_a.id, type="RECEIVE", quantity_delta=10, performed_by=owner_a_id)
            session.add(txn_a)
            await session.flush()
            medicine_a_id, batch_a_id, txn_a_id = medicine_a.id, batch_a.id, txn_a.id

        async with tenant_session(clinic_b.id) as session:
            medicine_b = Medicine(tenant_id=clinic_b.id, name="B")
            session.add(medicine_b)
            await session.flush()
            batch_b = MedicineBatch(tenant_id=clinic_b.id, medicine_id=medicine_b.id, batch_number="B1", expiry_date=date.today() + timedelta(days=30), quantity_on_hand=10)
            session.add(batch_b)
            await session.flush()
            session.add(PharmacyInventoryTransaction(tenant_id=clinic_b.id, batch_id=batch_b.id, type="RECEIVE", quantity_delta=10, performed_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            medicine_result = await session.execute(select(Medicine))
            visible_medicine_ids = {m.id for m in medicine_result.scalars().all()}
            batch_result = await session.execute(select(MedicineBatch))
            visible_batch_ids = {b.id for b in batch_result.scalars().all()}
            txn_result = await session.execute(select(PharmacyInventoryTransaction))
            visible_txn_ids = {t.id for t in txn_result.scalars().all()}

        assert visible_medicine_ids == {medicine_a_id}
        assert visible_batch_ids == {batch_a_id}
        assert visible_txn_ids == {txn_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
