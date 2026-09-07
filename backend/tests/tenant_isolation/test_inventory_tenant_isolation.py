"""Tenant-isolation suite for General (Non-Medicine) Inventory —
PRD-ARCHITECTURE.md §27. Same approach as every other module's suite:
prove isolation through the real HTTP API and through a deliberately
unscoped direct query (the RLS backstop) across both new tables.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.db import platform_admin_session, tenant_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.inventory.models import InventoryItem, InventoryTransaction
from app.modules.tenancy.models import Clinic

pytestmark = pytest.mark.usefixtures("require_db")


async def _create_clinic_with_owner(role_map: dict[str, uuid.UUID], *, email: str, password: str) -> tuple[Clinic, uuid.UUID]:
    slug = f"inventory-isolation-{uuid.uuid4().hex[:10]}"
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


async def test_item_created_in_one_tenant_is_invisible_via_api_in_another(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, _ = await _create_clinic_with_owner(role_map, email="owner@inventory-a.clinic", password="pw")
    clinic_b, _ = await _create_clinic_with_owner(role_map, email="owner@inventory-b.clinic", password="pw")

    try:
        headers_a = await _login(api_client, clinic_a, "owner@inventory-a.clinic", "pw")
        headers_b = await _login(api_client, clinic_b, "owner@inventory-b.clinic", "pw")

        created = await api_client.post(
            "/api/v1/inventory/items",
            json={"name": "TenantAItem", "category": "CONSUMABLE", "unit": "PIECES", "min_reorder_level": "5.00", "cost_per_unit": "1.00"},
            headers=headers_a,
        )
        assert created.status_code == 201
        item_id = created.json()["id"]

        list_b = await api_client.get("/api/v1/inventory/items", headers=headers_b)
        assert all(i["id"] != item_id for i in list_b.json()["items"])

        direct_b = await api_client.get(f"/api/v1/inventory/items/{item_id}", headers=headers_b)
        assert direct_b.status_code == 404

        direct_a = await api_client.get(f"/api/v1/inventory/items/{item_id}", headers=headers_a)
        assert direct_a.status_code == 200

        cross_tenant_txn = await api_client.post(
            f"/api/v1/inventory/items/{item_id}/transactions", json={"change_type": "PURCHASE", "quantity": "10.00"}, headers=headers_b
        )
        assert cross_tenant_txn.status_code == 404
    finally:
        await _teardown([clinic_a.id, clinic_b.id])


async def test_rls_blocks_even_a_deliberately_unscoped_inventory_query(api_client: AsyncClient, role_map: dict[str, uuid.UUID]) -> None:
    clinic_a, owner_a_id = await _create_clinic_with_owner(role_map, email="owner@inventory-c.clinic", password="pw")
    clinic_b, owner_b_id = await _create_clinic_with_owner(role_map, email="owner@inventory-d.clinic", password="pw")

    try:
        async with tenant_session(clinic_a.id) as session:
            item_a = InventoryItem(tenant_id=clinic_a.id, name="A", category="CONSUMABLE", unit="PIECES", min_reorder_level=Decimal("5"), cost_per_unit=Decimal("1"))
            session.add(item_a)
            await session.flush()
            txn_a = InventoryTransaction(tenant_id=clinic_a.id, item_id=item_a.id, change_type="PURCHASE", quantity=Decimal("10"), performed_by=owner_a_id)
            session.add(txn_a)
            await session.flush()
            item_a_id, txn_a_id = item_a.id, txn_a.id

        async with tenant_session(clinic_b.id) as session:
            item_b = InventoryItem(tenant_id=clinic_b.id, name="B", category="EQUIPMENT", unit="PACKS", min_reorder_level=Decimal("5"), cost_per_unit=Decimal("1"))
            session.add(item_b)
            await session.flush()
            session.add(InventoryTransaction(tenant_id=clinic_b.id, item_id=item_b.id, change_type="PURCHASE", quantity=Decimal("10"), performed_by=owner_b_id))

        async with tenant_session(clinic_a.id) as session:
            # No `.where(...tenant_id == ...)` — the app-layer mistake RLS
            # exists to catch.
            item_result = await session.execute(select(InventoryItem))
            visible_item_ids = {i.id for i in item_result.scalars().all()}
            txn_result = await session.execute(select(InventoryTransaction))
            visible_txn_ids = {t.id for t in txn_result.scalars().all()}

        assert visible_item_ids == {item_a_id}
        assert visible_txn_ids == {txn_a_id}
    finally:
        await _teardown([clinic_a.id, clinic_b.id])
