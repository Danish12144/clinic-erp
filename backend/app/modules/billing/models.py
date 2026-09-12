"""Billing, Invoices & Payments — PRD-ARCHITECTURE.md §4 (module list items
20/21/22), §5.1 (steps 11-12), §6, §17, migration 0014. See that
migration's docstring for the deliberate deviations from the master schema
(`DRAFT`/`ISSUED` states, `NET_BANKING` method, `invoice_line_items.
updated_at`, `payments.notes`).

`Invoice.status` is always *derived* from its `Payment` rows once ISSUED
(never set directly by the app, matching the master schema's own
invariant) — see `BillingService._recompute_status`. Line items are only
mutable while `DRAFT`; issuing locks them. `Payment` is DB-enforced
append-only as of migration 0031 (Phase 1 production-safety hardening) —
same `prevent_update_delete()` trigger as `Vitals`/`Prescription`/
`audit_logs`, plus a `REVOKE UPDATE, DELETE ... FROM app_user`. A refund
is a new negative-amount row, never an edit; there was never an update/
delete method for it in this module's repository either way, so no
application code changed — only the database now enforces what the app
already only ever did.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class InvoiceStatus(str, PyEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    VOID = "VOID"


invoice_status_enum = SAEnum(InvoiceStatus, name="invoice_status", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class InvoiceLineSource(str, PyEnum):
    CONSULTATION = "CONSULTATION"
    PROCEDURE = "PROCEDURE"
    PHARMACY = "PHARMACY"
    LAB = "LAB"
    OTHER = "OTHER"


invoice_line_source_enum = SAEnum(
    InvoiceLineSource, name="invoice_line_source", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class PaymentMethod(str, PyEnum):
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    NET_BANKING = "NET_BANKING"
    INSURANCE = "INSURANCE"
    OTHER = "OTHER"


payment_method_enum = SAEnum(PaymentMethod, name="payment_method", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    # Disambiguates multiple invoices against the same encounter (migration
    # 0030) -- reuses InvoiceLineSource rather than a parallel enum. OTHER
    # doubles as "general/ad-hoc, no single dominant source".
    source_type: Mapped[InvoiceLineSource] = mapped_column(
        invoice_line_source_enum, nullable=False, server_default=text("'OTHER'::invoice_line_source")
    )
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))
    status: Mapped[InvoiceStatus] = mapped_column(invoice_status_enum, nullable=False, server_default=text("'DRAFT'::invoice_status"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line_items: Mapped[list["InvoiceLineItem"]] = relationship(order_by="InvoiceLineItem.created_at")
    payments: Mapped[list["Payment"]] = relationship(order_by="Payment.recorded_at")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[InvoiceLineSource] = mapped_column(invoice_line_source_enum, nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("1"))
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(payment_method_enum, nullable=False)
    gateway_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
