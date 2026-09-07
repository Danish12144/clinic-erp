"""API surface for General (Non-Medicine) Inventory —
PRD-ARCHITECTURE.md §8: `/api/v1/inventory/*`.

`inventory.manage` (Owner) gates item create/update and every
`change_type` on a transaction. `inventory.record_usage`
(Receptionist/Nurse/Other Staff) and `inventory.view` (Doctor, read-only)
both reach the read routes via `require_any_permission`; only
`inventory.record_usage` additionally reaches the transactions route — a
route-level permission check alone can't restrict *which* `change_type`
a caller may submit there, so `InventoryService.record_transaction` enforces
the USAGE-only tier for non-Owner callers itself (see that method's
docstring).
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_permission
from app.modules.inventory.models import InventoryItemCategory
from app.modules.inventory.schemas import (
    InventoryItemCreateRequest,
    InventoryItemListResponse,
    InventoryItemSummary,
    InventoryItemUpdateRequest,
    InventoryTransactionCreateRequest,
    InventoryTransactionSummary,
)
from app.modules.inventory.service import InventoryService

_READ_PERMS = ("inventory.manage", "inventory.record_usage", "inventory.view")
_TRANSACTION_PERMS = ("inventory.manage", "inventory.record_usage")

items_router = APIRouter(prefix="/api/v1/inventory/items", tags=["inventory"])
alerts_router = APIRouter(prefix="/api/v1/inventory/alerts", tags=["inventory"])


def get_inventory_service() -> InventoryService:
    return InventoryService()


# ---- Items ------------------------------------------------------------------------


@items_router.post("", response_model=InventoryItemSummary, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: InventoryItemCreateRequest,
    current_user: CurrentUser = Depends(require_permission("inventory.manage")),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryItemSummary:
    return await service.create_item(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@items_router.get("", response_model=InventoryItemListResponse)
async def search_items(
    category: InventoryItemCategory | None = Query(None),
    is_active: bool | None = Query(None),
    low_stock_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryItemListResponse:
    return await service.search_items(
        tenant_id=current_user.tenant_id, category=category, is_active=is_active, low_stock_only=low_stock_only, limit=limit, offset=offset,
    )


@items_router.get("/{item_id}", response_model=InventoryItemSummary)
async def get_item(
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryItemSummary:
    return await service.get_item(tenant_id=current_user.tenant_id, item_id=item_id)


@items_router.patch("/{item_id}", response_model=InventoryItemSummary)
async def update_item(
    item_id: uuid.UUID,
    payload: InventoryItemUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("inventory.manage")),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryItemSummary:
    return await service.update_item(tenant_id=current_user.tenant_id, item_id=item_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@items_router.post("/{item_id}/transactions", response_model=InventoryTransactionSummary, status_code=status.HTTP_201_CREATED)
async def record_transaction(
    item_id: uuid.UUID,
    payload: InventoryTransactionCreateRequest,
    current_user: CurrentUser = Depends(require_any_permission(*_TRANSACTION_PERMS)),
    service: InventoryService = Depends(get_inventory_service),
) -> InventoryTransactionSummary:
    return await service.record_transaction(
        tenant_id=current_user.tenant_id, item_id=item_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code,
    )


# ---- Alerts -------------------------------------------------------------------------


@alerts_router.get("/low-stock", response_model=list[InventoryItemSummary])
async def list_low_stock_alerts(
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: InventoryService = Depends(get_inventory_service),
) -> list[InventoryItemSummary]:
    return await service.list_low_stock_alerts(tenant_id=current_user.tenant_id)
