import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.inventory.models import InventoryChangeType, InventoryItemCategory, InventoryUnit


class InventoryItemCreateRequest(BaseModel):
    """No `current_stock` field — every item starts at 0 and stock only
    ever enters via a `PURCHASE` transaction, same "stock is a ledger, not
    a value you can just set" discipline Pharmacy's `Medicine` uses."""

    name: str = Field(..., min_length=1, max_length=300)
    category: InventoryItemCategory
    unit: InventoryUnit
    min_reorder_level: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    cost_per_unit: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)


class InventoryItemUpdateRequest(BaseModel):
    """Metadata only — `current_stock` is never editable here; it only
    ever changes via `POST .../transactions`."""

    name: str | None = Field(None, min_length=1, max_length=300)
    category: InventoryItemCategory | None = None
    unit: InventoryUnit | None = None
    min_reorder_level: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    cost_per_unit: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "InventoryItemUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class InventoryItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    category: InventoryItemCategory
    unit: InventoryUnit
    current_stock: Decimal
    min_reorder_level: Decimal
    cost_per_unit: Decimal
    is_active: bool
    is_below_reorder_level: bool
    created_at: datetime
    updated_at: datetime


class InventoryItemListResponse(BaseModel):
    items: list[InventoryItemSummary]
    total: int
    limit: int
    offset: int


# ---- Transactions -------------------------------------------------------------


class InventoryTransactionCreateRequest(BaseModel):
    """`quantity` is always a positive magnitude for `PURCHASE`/`USAGE`/
    `RETURN` (the `change_type` alone determines whether it increases or
    decreases `current_stock`); only `ADJUSTMENT` accepts either sign,
    applied directly, since it's a manual correction that can go either
    way. See `InventoryService.record_transaction` for the delta math."""

    change_type: InventoryChangeType
    quantity: Decimal = Field(..., max_digits=10, decimal_places=2)
    reference_id: uuid.UUID | None = Field(None, description="Opaque pointer only — no target table specified, no FK")
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def quantity_sign_matches_change_type(self) -> "InventoryTransactionCreateRequest":
        if self.quantity == 0:
            raise ValueError("quantity must not be zero")
        if self.change_type != InventoryChangeType.ADJUSTMENT and self.quantity < 0:
            raise ValueError(f"quantity must be positive for {self.change_type.value}")
        return self


class InventoryTransactionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    item_id: uuid.UUID
    change_type: InventoryChangeType
    quantity: Decimal
    reference_id: uuid.UUID | None
    performed_by: uuid.UUID
    notes: str | None
    created_at: datetime
    resulting_stock: Decimal
