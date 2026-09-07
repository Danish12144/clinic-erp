"""General (Non-Medicine) Inventory business logic — see
app/modules/inventory/models.py's module docstring and
PRD-ARCHITECTURE.md §6, migration 0022.

`record_transaction` is the one method that touches both
`inventory_items` and `inventory_transactions` atomically in a single DB
transaction: apply the signed delta to `current_stock` via
`InventoryItemRepository.apply_delta`'s atomic conditional UPDATE (fails
closed on insufficient stock, no explicit lock needed — same pattern as
Pharmacy's dispense/checkout), then insert the ledger row. Any failure
partway rolls back the whole thing, since it's all one `tenant_session`.

**RBAC tier enforcement for `record_transaction` lives here, not in the
router** — the route accepts every `change_type` from one shared endpoint
(unlike Expenses, which could split `.manage`-only writes onto a separate
`PATCH` route), so a Receptionist/Nurse/Other-Staff caller (who only holds
`inventory.record_usage`, not `inventory.manage`) is allowed through the
route's `require_any_permission` gate but then rejected here with 403 if
`change_type` isn't `USAGE`. Owner/Admin collapses to the single `OWNER`
role code, since no separate "Admin" role exists in this system's 8-role
model.
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.inventory.models import InventoryChangeType, InventoryItem, InventoryItemCategory
from app.modules.inventory.repository import InventoryItemRepository, InventoryTransactionRepository
from app.modules.inventory.schemas import (
    InventoryItemCreateRequest,
    InventoryItemListResponse,
    InventoryItemSummary,
    InventoryItemUpdateRequest,
    InventoryTransactionCreateRequest,
    InventoryTransactionSummary,
)


def _to_item_summary(item: InventoryItem) -> InventoryItemSummary:
    return InventoryItemSummary(
        id=item.id, tenant_id=item.tenant_id, name=item.name, category=item.category, unit=item.unit,
        current_stock=item.current_stock, min_reorder_level=item.min_reorder_level, cost_per_unit=item.cost_per_unit,
        is_active=item.is_active, is_below_reorder_level=Decimal(str(item.current_stock)) < Decimal(str(item.min_reorder_level)),
        created_at=item.created_at, updated_at=item.updated_at,
    )


class InventoryService:
    # ---- Items -----------------------------------------------------------------

    async def create_item(self, *, tenant_id: uuid.UUID, payload: InventoryItemCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InventoryItemSummary:
        async with tenant_session(tenant_id) as session:
            item = await InventoryItemRepository(session).create(tenant_id=tenant_id, **payload.model_dump())
            summary = _to_item_summary(item)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="inventory_item.create", entity_type="inventory_item", entity_id=item.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_item(self, *, tenant_id: uuid.UUID, item_id: uuid.UUID, payload: InventoryItemUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InventoryItemSummary:
        async with tenant_session(tenant_id) as session:
            repo = InventoryItemRepository(session)
            item = await repo.get_by_id(item_id)
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory item not found")
            before = _to_item_summary(item).model_dump(mode="json")

            changes = payload.model_dump(exclude_unset=True)
            await repo.update_fields(item_id, **changes)
            updated = await repo.get_by_id(item_id)
            assert updated is not None
            after = _to_item_summary(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="inventory_item.update", entity_type="inventory_item", entity_id=item_id, before=before, after=after.model_dump(mode="json"),
            )
            return after

    async def get_item(self, *, tenant_id: uuid.UUID, item_id: uuid.UUID) -> InventoryItemSummary:
        async with tenant_session(tenant_id) as session:
            item = await InventoryItemRepository(session).get_by_id(item_id)
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory item not found")
            return _to_item_summary(item)

    async def search_items(
        self, *, tenant_id: uuid.UUID, category: InventoryItemCategory | None, is_active: bool | None,
        low_stock_only: bool, limit: int, offset: int,
    ) -> InventoryItemListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await InventoryItemRepository(session).search(
                tenant_id=tenant_id, category=category, is_active=is_active, low_stock_only=low_stock_only, limit=limit, offset=offset,
            )
            return InventoryItemListResponse(items=[_to_item_summary(i) for i in rows], total=total, limit=limit, offset=offset)

    async def list_low_stock_alerts(self, *, tenant_id: uuid.UUID) -> list[InventoryItemSummary]:
        async with tenant_session(tenant_id) as session:
            rows = await InventoryItemRepository(session).list_low_stock(tenant_id=tenant_id)
            return [_to_item_summary(i) for i in rows]

    # ---- Transactions ------------------------------------------------------------

    async def record_transaction(
        self, *, tenant_id: uuid.UUID, item_id: uuid.UUID, payload: InventoryTransactionCreateRequest, actor_user_id: uuid.UUID, actor_role: str,
    ) -> InventoryTransactionSummary:
        if actor_role != "OWNER" and payload.change_type != InventoryChangeType.USAGE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only USAGE transactions can be logged by this role")

        async with tenant_session(tenant_id) as session:
            item_repo = InventoryItemRepository(session)
            item = await item_repo.get_by_id(item_id)
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory item not found")

            # USAGE always decreases stock; PURCHASE/RETURN always increase
            # it; ADJUSTMENT applies the caller's signed quantity directly
            # (the schema's own validator already rejects a negative
            # quantity for every type except ADJUSTMENT).
            delta = -payload.quantity if payload.change_type == InventoryChangeType.USAGE else payload.quantity

            if not await item_repo.apply_delta(item_id, delta):
                raise HTTPException(status.HTTP_409_CONFLICT, "This transaction would take current_stock below zero")

            txn = await InventoryTransactionRepository(session).create(
                tenant_id=tenant_id, item_id=item_id, change_type=payload.change_type, quantity=payload.quantity,
                reference_id=payload.reference_id, performed_by=actor_user_id, notes=payload.notes,
            )

            updated_item = await item_repo.get_by_id(item_id)
            assert updated_item is not None

            summary = InventoryTransactionSummary(
                id=txn.id, tenant_id=tenant_id, item_id=item_id, change_type=txn.change_type, quantity=txn.quantity,
                reference_id=txn.reference_id, performed_by=txn.performed_by, notes=txn.notes, created_at=txn.created_at,
                resulting_stock=updated_item.current_stock,
            )
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="inventory_transaction.create", entity_type="inventory_item", entity_id=item_id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary
