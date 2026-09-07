"""End-to-end tests of the General (Non-Medicine) Inventory HTTP surface
(item CRUD, transaction ledger, negative-stock guard, low-stock alerts,
RBAC, audit trail) against a real Postgres — see tests/conftest.py
(skipped automatically if unreachable).
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.usefixtures("require_db")


def _item_payload(**overrides) -> dict:
    payload = {"name": "Gauze Rolls", "category": "CONSUMABLE", "unit": "BOXES", "min_reorder_level": "10.00", "cost_per_unit": "50.00"}
    payload.update(overrides)
    return payload


async def _create_item(api_client: AsyncClient, owner_headers: dict[str, str], **overrides) -> str:
    response = await api_client.post("/api/v1/inventory/items", json=_item_payload(**overrides), headers=owner_headers)
    assert response.status_code == 201
    return response.json()["id"]


async def _transact(api_client: AsyncClient, headers: dict[str, str], item_id: str, **overrides) -> dict:
    payload = {"change_type": "PURCHASE", "quantity": "10.00"}
    payload.update(overrides)
    return await api_client.post(f"/api/v1/inventory/items/{item_id}/transactions", json=payload, headers=headers)


# ---- Item CRUD / RBAC ---------------------------------------------------------------


async def test_owner_can_create_and_read_an_item(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.post("/api/v1/inventory/items", json=_item_payload(), headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "CONSUMABLE"
    assert body["unit"] == "BOXES"
    assert body["current_stock"] == "0.00"
    assert body["is_active"] is True

    fetched = await api_client.get(f"/api/v1/inventory/items/{body['id']}", headers=owner_headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Gauze Rolls"


async def test_owner_can_update_an_item(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers)
    response = await api_client.patch(f"/api/v1/inventory/items/{item_id}", json={"cost_per_unit": "60.00", "is_active": False}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["cost_per_unit"] == "60.00"
    assert response.json()["is_active"] is False
    assert response.json()["name"] == "Gauze Rolls"  # untouched field preserved


async def test_updating_current_stock_directly_is_not_possible(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers)
    # current_stock isn't a field on the update schema at all — smuggling
    # it in alongside a real field must be silently ignored, not applied.
    response = await api_client.patch(f"/api/v1/inventory/items/{item_id}", json={"cost_per_unit": "5.00", "current_stock": "999.00"}, headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["cost_per_unit"] == "5.00"
    assert response.json()["current_stock"] == "0.00"


async def test_updating_a_nonexistent_item_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.patch("/api/v1/inventory/items/00000000-0000-0000-0000-000000000000", json={"cost_per_unit": "1.00"}, headers=owner_headers)
    assert response.status_code == 404


async def test_get_nonexistent_item_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await api_client.get("/api/v1/inventory/items/00000000-0000-0000-0000-000000000000", headers=owner_headers)
    assert response.status_code == 404


async def test_receptionist_nurse_and_other_staff_can_read_but_not_create_or_update(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    item_id = await _create_item(api_client, owner_headers, name="ReadOnlyRoleItem")
    for role in ("RECEPTIONIST", "NURSE", "OTHER_STAFF"):
        headers, _ = await login_as(role_code=role)
        read = await api_client.get("/api/v1/inventory/items", headers=headers)
        assert read.status_code == 200, role
        create = await api_client.post("/api/v1/inventory/items", json=_item_payload(), headers=headers)
        assert create.status_code == 403, role
        update = await api_client.patch(f"/api/v1/inventory/items/{item_id}", json={"cost_per_unit": "1.00"}, headers=headers)
        assert update.status_code == 403, role


async def test_doctor_is_read_only(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    item_id = await _create_item(api_client, owner_headers, name="DoctorReadItem")
    headers, _ = await login_as(role_code="DOCTOR")

    read = await api_client.get("/api/v1/inventory/items", headers=headers)
    assert read.status_code == 200
    create = await api_client.post("/api/v1/inventory/items", json=_item_payload(), headers=headers)
    assert create.status_code == 403
    txn = await _transact(api_client, headers, item_id, change_type="USAGE", quantity="1.00")
    assert txn.status_code == 403


async def test_lab_staff_and_pharmacy_staff_have_zero_access(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    for role in ("LAB_STAFF", "PHARMACY_STAFF"):
        headers, _ = await login_as(role_code=role)
        read = await api_client.get("/api/v1/inventory/items", headers=headers)
        assert read.status_code == 403, role


# ---- Transactions / ledger ----------------------------------------------------------


async def test_purchase_and_usage_update_current_stock(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="LedgerItem")

    purchase = await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="20.00")
    assert purchase.status_code == 201
    assert purchase.json()["resulting_stock"] == "20.00"

    usage = await _transact(api_client, owner_headers, item_id, change_type="USAGE", quantity="5.00")
    assert usage.status_code == 201
    assert usage.json()["resulting_stock"] == "15.00"

    fetched = await api_client.get(f"/api/v1/inventory/items/{item_id}", headers=owner_headers)
    assert fetched.json()["current_stock"] == "15.00"


async def test_return_increases_stock_and_adjustment_applies_signed_quantity(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="ReturnAdjustItem")
    await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="10.00")

    returned = await _transact(api_client, owner_headers, item_id, change_type="RETURN", quantity="3.00")
    assert returned.status_code == 201
    assert returned.json()["resulting_stock"] == "13.00"

    negative_adjustment = await _transact(api_client, owner_headers, item_id, change_type="ADJUSTMENT", quantity="-4.00")
    assert negative_adjustment.status_code == 201
    assert negative_adjustment.json()["resulting_stock"] == "9.00"

    positive_adjustment = await _transact(api_client, owner_headers, item_id, change_type="ADJUSTMENT", quantity="1.50")
    assert positive_adjustment.status_code == 201
    assert positive_adjustment.json()["resulting_stock"] == "10.50"


async def test_negative_stock_is_rejected_for_usage(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="NegativeStockItem")
    await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="5.00")

    overdraw = await _transact(api_client, owner_headers, item_id, change_type="USAGE", quantity="10.00")
    assert overdraw.status_code == 409

    unchanged = await api_client.get(f"/api/v1/inventory/items/{item_id}", headers=owner_headers)
    assert unchanged.json()["current_stock"] == "5.00"


async def test_negative_stock_is_rejected_for_a_large_negative_adjustment(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="NegativeAdjustItem")
    await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="5.00")

    overdraw = await _transact(api_client, owner_headers, item_id, change_type="ADJUSTMENT", quantity="-10.00")
    assert overdraw.status_code == 409

    unchanged = await api_client.get(f"/api/v1/inventory/items/{item_id}", headers=owner_headers)
    assert unchanged.json()["current_stock"] == "5.00"


async def test_zero_quantity_is_rejected(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="ZeroQtyItem")
    response = await _transact(api_client, owner_headers, item_id, change_type="ADJUSTMENT", quantity="0")
    assert response.status_code == 422


async def test_negative_quantity_is_rejected_for_non_adjustment_types(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="NegNonAdjustItem")
    for change_type in ("PURCHASE", "USAGE", "RETURN"):
        response = await _transact(api_client, owner_headers, item_id, change_type=change_type, quantity="-5.00")
        assert response.status_code == 422, change_type


async def test_transaction_against_nonexistent_item_is_404(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    response = await _transact(api_client, owner_headers, "00000000-0000-0000-0000-000000000000", change_type="PURCHASE", quantity="1.00")
    assert response.status_code == 404


async def test_receptionist_nurse_and_other_staff_can_only_log_usage(api_client: AsyncClient, owner_headers: dict[str, str], login_as) -> None:
    for role in ("RECEPTIONIST", "NURSE", "OTHER_STAFF"):
        item_id = await _create_item(api_client, owner_headers, name=f"UsageOnlyItem-{role}")
        await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="20.00")
        headers, _ = await login_as(role_code=role)

        usage = await _transact(api_client, headers, item_id, change_type="USAGE", quantity="2.00")
        assert usage.status_code == 201, role
        assert usage.json()["resulting_stock"] == "18.00"

        for change_type in ("PURCHASE", "ADJUSTMENT", "RETURN"):
            blocked = await _transact(api_client, headers, item_id, change_type=change_type, quantity="1.00")
            assert blocked.status_code == 403, (role, change_type)


# ---- Search filters + low-stock alerts -----------------------------------------------


async def test_search_filters_by_category(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    consumable_id = await _create_item(api_client, owner_headers, name="FilterConsumable", category="CONSUMABLE")
    equipment_id = await _create_item(api_client, owner_headers, name="FilterEquipment", category="EQUIPMENT")

    response = await api_client.get("/api/v1/inventory/items?category=EQUIPMENT", headers=owner_headers)
    assert response.status_code == 200
    ids = {i["id"] for i in response.json()["items"]}
    assert equipment_id in ids
    assert consumable_id not in ids


async def test_low_stock_only_filter_and_alerts_endpoint(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    low_id = await _create_item(api_client, owner_headers, name="LowStockAlertItem", min_reorder_level="100.00")
    high_id = await _create_item(api_client, owner_headers, name="HighStockAlertItem", min_reorder_level="5.00")
    await _transact(api_client, owner_headers, low_id, change_type="PURCHASE", quantity="10.00")
    await _transact(api_client, owner_headers, high_id, change_type="PURCHASE", quantity="10.00")

    filtered = await api_client.get("/api/v1/inventory/items?low_stock_only=true", headers=owner_headers)
    assert filtered.status_code == 200
    filtered_ids = {i["id"] for i in filtered.json()["items"]}
    assert low_id in filtered_ids
    assert high_id not in filtered_ids

    alerts = await api_client.get("/api/v1/inventory/alerts/low-stock", headers=owner_headers)
    assert alerts.status_code == 200
    alert_ids = {i["id"] for i in alerts.json()}
    assert low_id in alert_ids
    assert high_id not in alert_ids


async def test_low_stock_alerts_excludes_inactive_items(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="InactiveLowStockItem", min_reorder_level="100.00")
    await api_client.patch(f"/api/v1/inventory/items/{item_id}", json={"is_active": False}, headers=owner_headers)

    alerts = await api_client.get("/api/v1/inventory/alerts/low-stock", headers=owner_headers)
    assert alerts.status_code == 200
    assert all(i["id"] != item_id for i in alerts.json())


# ---- Audit trail ----------------------------------------------------------------------


async def test_item_create_and_transaction_are_audited(api_client: AsyncClient, owner_headers: dict[str, str]) -> None:
    item_id = await _create_item(api_client, owner_headers, name="AuditedItem")
    await _transact(api_client, owner_headers, item_id, change_type="PURCHASE", quantity="7.00")

    logs = await api_client.get("/api/v1/audit-logs", headers=owner_headers)
    assert logs.status_code == 200
    actions = {entry["action"] for entry in logs.json()["items"] if entry["entity_id"] == item_id}
    assert "inventory_item.create" in actions
    assert "inventory_transaction.create" in actions
