import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.expenses.models import ExpenseCategory, ExpensePaymentMode


class ExpenseCreateRequest(BaseModel):
    branch_id: uuid.UUID
    category: ExpenseCategory
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    expense_date: date | None = Field(None, description="Defaults to today if omitted")
    payment_mode: ExpensePaymentMode
    vendor: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=1000)
    receipt_document_id: uuid.UUID | None = Field(None, description="Opaque pointer only — no Documents module exists yet to validate it against")


class ExpenseUpdateRequest(BaseModel):
    branch_id: uuid.UUID | None = None
    category: ExpenseCategory | None = None
    amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    expense_date: date | None = None
    payment_mode: ExpensePaymentMode | None = None
    vendor: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=1000)
    receipt_document_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ExpenseUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ExpenseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    category: str
    amount: Decimal
    expense_date: date
    payment_mode: str
    vendor: str | None
    notes: str | None
    receipt_document_id: uuid.UUID | None
    recorded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ExpenseListResponse(BaseModel):
    items: list[ExpenseSummary]
    total: int
    limit: int
    offset: int
    total_amount: Decimal = Field(..., description="Sum of `amount` across every row matching the current filters, not just this page")
