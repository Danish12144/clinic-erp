import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.billing.models import PaymentMethod
from app.modules.pharmacy.models import PharmacySaleStatus


class MedicineCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    generic_name: str | None = Field(None, max_length=300)
    category: str | None = Field(None, max_length=200)
    dosage_form: str | None = Field(None, max_length=100)
    strength: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=300)
    unit_price: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    sku: str | None = Field(None, max_length=100)
    reorder_threshold: int = Field(0, ge=0)


class MedicineUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    generic_name: str | None = Field(None, max_length=300)
    category: str | None = Field(None, max_length=200)
    dosage_form: str | None = Field(None, max_length=100)
    strength: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=300)
    unit_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    sku: str | None = Field(None, max_length=100)
    reorder_threshold: int | None = Field(None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "MedicineUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class MedicineSummary(BaseModel):
    """`total_stock`/`is_below_reorder_threshold` are computed by the
    service (summed across the medicine's batches) — not plain ORM
    columns, so this is never built via a bare `model_validate(medicine)`."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    generic_name: str | None
    category: str | None
    dosage_form: str | None
    strength: str | None
    manufacturer: str | None
    unit_price: Decimal
    sku: str | None
    reorder_threshold: int
    is_active: bool
    total_stock: int
    is_below_reorder_threshold: bool
    created_at: datetime
    updated_at: datetime


class MedicineListResponse(BaseModel):
    items: list[MedicineSummary]
    total: int
    limit: int
    offset: int


# ---- Batches / receiving stock ----------------------------------------------


class ReceiveStockRequest(BaseModel):
    batch_number: str = Field(..., min_length=1, max_length=200)
    expiry_date: date
    quantity: int = Field(..., ge=1, le=1_000_000)
    cost_price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)


class MedicineBatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    medicine_id: uuid.UUID
    batch_number: str
    expiry_date: date
    quantity_on_hand: int
    cost_price: Decimal | None
    created_at: datetime
    updated_at: datetime


class MedicineBatchListResponse(BaseModel):
    items: list[MedicineBatchSummary]
    total: int
    limit: int
    offset: int


# ---- Dispensing ---------------------------------------------------------------


class DispenseRequest(BaseModel):
    prescription_item_id: uuid.UUID
    quantity: int = Field(..., ge=1, le=100_000)


class DispenseAllocation(BaseModel):
    batch_id: uuid.UUID
    batch_number: str
    quantity: int


class DispenseResult(BaseModel):
    prescription_item_id: uuid.UUID
    medicine_id: uuid.UUID
    quantity_dispensed: int
    prescription_item_dispensed_quantity: int
    allocations: list[DispenseAllocation]


# ---- OTC / Retail sales ---------------------------------------------------------


class OTCSaleCartItem(BaseModel):
    medicine_id: uuid.UUID
    quantity: int = Field(..., ge=1, le=100_000)


class OTCSaleCreateRequest(BaseModel):
    customer_name: str | None = Field(None, max_length=300)
    customer_phone: str | None = Field(None, max_length=50)
    items: list[OTCSaleCartItem] = Field(..., min_length=1)
    discount_amount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    payment_mode: PaymentMethod


class SaleItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    medicine_id: uuid.UUID
    batch_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    total_price: Decimal


class SaleSummary(BaseModel):
    """The sale row *is* the receipt — no separate bill/invoice entity, see
    migration 0021's docstring."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    customer_name: str | None
    customer_phone: str | None
    total_amount: Decimal
    discount_amount: Decimal
    net_amount: Decimal
    payment_mode: PaymentMethod
    status: PharmacySaleStatus
    created_by: uuid.UUID
    created_at: datetime
    items: list[SaleItemSummary]


class SaleListResponse(BaseModel):
    items: list[SaleSummary]
    total: int
    limit: int
    offset: int
    total_net_amount: Decimal = Field(..., description="Sum of `net_amount` across every sale matching the current filters, not just this page")
