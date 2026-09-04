"""Pharmacy & Inventory Management — PRD-ARCHITECTURE.md §4 (module list
items 24/25), §18, §6, migration 0017. See that migration's docstring for
the deliberate schema additions (`strength`/`manufacturer`/
`reorder_threshold` on `medicines`) and the fulfilled `prescription_items.
medicine_id` FK.

"Stock is a ledger, not a mutable counter" (PRD §18): `MedicineBatch.
quantity_on_hand` is a denormalized running total, updated only alongside
a `PharmacyInventoryTransaction` insert in the same DB transaction — see
`PharmacyService.dispense_prescription_item` and `receive_stock`. Never
write `quantity_on_hand` directly from anywhere else.
"""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InventoryTransactionType(str, PyEnum):
    RECEIVE = "RECEIVE"
    DISPENSE = "DISPENSE"
    SALE = "SALE"
    ADJUST = "ADJUST"
    EXPIRE_WRITE_OFF = "EXPIRE_WRITE_OFF"


inventory_txn_type_enum = SAEnum(
    InventoryTransactionType, name="inventory_txn_type", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    generic_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(Text, nullable=True)
    strength: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    sku: Mapped[str | None] = mapped_column(Text, nullable=True)
    reorder_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MedicineBatch(Base):
    __tablename__ = "medicine_batches"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    medicine_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)
    batch_number: Mapped[str] = mapped_column(Text, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PharmacyInventoryTransaction(Base):
    __tablename__ = "pharmacy_inventory_transactions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("medicine_batches.id"), nullable=False)
    type: Mapped[InventoryTransactionType] = mapped_column(inventory_txn_type_enum, nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
