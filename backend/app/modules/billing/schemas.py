import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.billing.models import InvoiceLineSource, PaymentMethod


class InvoiceLineItemCreateRequest(BaseModel):
    source_type: InvoiceLineSource
    source_id: uuid.UUID | None = None
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(Decimal("1"), gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)


class InvoiceCreateRequest(BaseModel):
    branch_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    # Disambiguates this invoice from any other non-VOID invoice already
    # raised for the same encounter (see auto_generate_invoice's own
    # duplicate guard) — defaults to OTHER ("general/ad-hoc") for a
    # manually built invoice that doesn't map to one clean source.
    source_type: InvoiceLineSource = InvoiceLineSource.OTHER
    line_items: list[InvoiceLineItemCreateRequest] = Field(default_factory=list, max_length=100)
    tax: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    discount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class AutoGenerateInvoiceRequest(BaseModel):
    """The "automatic" path (PRD item 20): pulls the doctor's configured
    `consultation_fee` for the encounter's `Consultation` into a single
    CONSULTATION line item. 422s if there's no consultation for the
    encounter yet, or the doctor has no fee configured — there is nothing
    to auto-generate from. Procedures/other charges still need the manual
    line-item endpoints; this only ever produces the one line."""

    encounter_id: uuid.UUID


class InvoiceLineItemUpdateRequest(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=500)
    quantity: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "InvoiceLineItemUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class InvoiceUpdateRequest(BaseModel):
    """Invoice-level fields, editable only while `DRAFT` — same rule as
    line items."""

    tax: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    discount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "InvoiceUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class InvoiceVoidRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class PaymentCreateRequest(BaseModel):
    """A positive `amount` records a payment; a negative `amount` records
    a refund (PRD §17 — never mutates/deletes a prior payment, always a
    new row). Zero is meaningless either way."""

    invoice_id: uuid.UUID
    amount: Decimal = Field(..., max_digits=12, decimal_places=2)
    method: PaymentMethod
    gateway_reference: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def amount_is_nonzero(self) -> "PaymentCreateRequest":
        if self.amount == 0:
            raise ValueError("amount must not be zero")
        return self


class InvoiceLineItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    created_at: datetime
    updated_at: datetime


class PaymentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    method: str
    gateway_reference: str | None
    notes: str | None
    recorded_by: uuid.UUID
    # PRD's "received_by" concept — same column (Payment.recorded_by),
    # resolved to a display name so the UI doesn't have to show a raw
    # UUID. None only if the recording user's own record was hard-deleted
    # (never happens today — users are soft-deactivated, not deleted).
    recorded_by_name: str | None = None
    recorded_at: datetime


class PaymentOrderResponse(BaseModel):
    """A simulated gateway order/intent (§17) — not a `Payment`. The
    actual payment is still only ever recorded via
    `POST /api/v1/billing/payments` once it's confirmed (today: a staff
    member keys it in after collecting it; a real gateway integration
    would instead confirm it via webhook)."""

    invoice_id: uuid.UUID
    order_id: str
    amount: Decimal
    currency: str
    provider: str
    status: str


class InvoiceSummary(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    encounter_id: uuid.UUID | None
    patient_id: uuid.UUID
    source_type: str
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    status: str
    # A simplified 4-value projection of `status` (DRAFT/ISSUED both read
    # as UNPAID) for callers that just want "is this paid, partially, or
    # not at all" without the DRAFT/ISSUED distinction that only matters
    # for whether line items are still editable. `status` remains the
    # source of truth and the only field any transition logic reads.
    payment_status: str
    voided_at: datetime | None
    voided_reason: str | None
    # total_paid/balance_due are the original field names (kept for
    # backward compatibility with every existing caller); paid_amount/
    # outstanding_amount are the same two values under the PRD's own
    # naming — both always identical, pick whichever reads better at the
    # call site.
    total_paid: Decimal
    balance_due: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    created_at: datetime
    updated_at: datetime
    line_items: list[InvoiceLineItemSummary]
    payments: list[PaymentSummary]


class InvoiceListResponse(BaseModel):
    items: list[InvoiceSummary]
    total: int
    limit: int
    offset: int


class PaymentListResponse(BaseModel):
    items: list[PaymentSummary]
    total: int
    limit: int
    offset: int
