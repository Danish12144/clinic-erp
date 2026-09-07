"""General (Non-Medicine) Inventory — PRD-ARCHITECTURE.md §4 (module list
item 26), §6, migration 0022. See that migration's docstring for the
deliberate deviations from the master schema's `inventory_items`/
`inventory_transactions` sketch (real `category`/`unit` enums, this task's
own column names, `cost_per_unit`/`is_active` gap-fills, no `branch_id`,
and a wholly new `inventory_change_type` enum distinct from Pharmacy's
`inventory_txn_type`).

`current_stock` is a ledger total, the same "never write it directly
outside a transaction insert" discipline `MedicineBatch.quantity_on_hand`
established — see `InventoryService.record_transaction` and
`InventoryItemRepository.apply_delta`.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, ForeignKey, Numeric, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InventoryItemCategory(str, PyEnum):
    CONSUMABLE = "CONSUMABLE"
    EQUIPMENT = "EQUIPMENT"
    LAB_SUPPLY = "LAB_SUPPLY"
    OFFICE = "OFFICE"


inventory_item_category_enum = SAEnum(
    InventoryItemCategory, name="inventory_item_category", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class InventoryUnit(str, PyEnum):
    PIECES = "PIECES"
    PACKS = "PACKS"
    BOXES = "BOXES"


inventory_unit_enum = SAEnum(InventoryUnit, name="inventory_unit", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class InventoryChangeType(str, PyEnum):
    PURCHASE = "PURCHASE"
    USAGE = "USAGE"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"


inventory_change_type_enum = SAEnum(
    InventoryChangeType, name="inventory_change_type", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[InventoryItemCategory] = mapped_column(inventory_item_category_enum, nullable=False)
    unit: Mapped[InventoryUnit] = mapped_column(inventory_unit_enum, nullable=False)
    current_stock: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    min_reorder_level: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    cost_per_unit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryTransaction(Base):
    """Append-by-convention ledger row (like `payments`/
    `pharmacy_inventory_transactions` — not DB-enforced append-only via
    `prevent_update_delete()`, that mechanism is reserved for
    `vitals`/`prescriptions`/`audit_logs`). No update/delete method exists
    in this module's repository either way."""

    __tablename__ = "inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    change_type: Mapped[InventoryChangeType] = mapped_column(inventory_change_type_enum, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
