import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReferenceRangeEntry(BaseModel):
    """One row of a test's reference range table — `sex`/`age_min`/
    `age_max` are all optional; omitted means "applies regardless." See
    migration 0018's docstring for why this is an array, not a bare
    object."""

    min: float | None = None
    max: float | None = None
    unit: str | None = Field(None, max_length=50)
    sex: str | None = Field(None, pattern="^(Male|Female|Other)$")
    age_min: float | None = Field(None, ge=0)
    age_max: float | None = Field(None, ge=0)


# ---- Catalog --------------------------------------------------------------------


class LabTestCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    test_code: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=200)
    specimen_type: str | None = Field(None, max_length=200)
    turnaround_hours: int | None = Field(None, ge=0, le=100_000)
    price: Decimal = Field(Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    reference_ranges: list[ReferenceRangeEntry] = Field(default_factory=list, max_length=50)


class LabTestUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=300)
    test_code: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=200)
    specimen_type: str | None = Field(None, max_length=200)
    turnaround_hours: int | None = Field(None, ge=0, le=100_000)
    price: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    reference_ranges: list[ReferenceRangeEntry] | None = Field(None, max_length=50)
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "LabTestUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class LabTestSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    test_code: str | None
    category: str | None
    specimen_type: str | None
    turnaround_hours: int | None
    price: Decimal
    reference_ranges: list[ReferenceRangeEntry]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LabTestListResponse(BaseModel):
    items: list[LabTestSummary]
    total: int
    limit: int
    offset: int


# ---- Orders ---------------------------------------------------------------------


class LabOrderCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    test_id: uuid.UUID
    doctor_id: uuid.UUID | None = Field(None, description="The clinically-ordering doctor; defaults to the caller when they are themselves a Doctor")


class LabOrderCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class LabResultEntry(BaseModel):
    parameter: str = Field(..., min_length=1, max_length=300)
    value: str = Field(..., min_length=1, max_length=500)
    unit: str | None = Field(None, max_length=50)
    flag_override: str | None = Field(None, description="Manually force NORMAL/LOW/HIGH/CRITICAL instead of auto-flagging against the catalog's reference ranges")


class LabResultCreateRequest(BaseModel):
    results: list[LabResultEntry] = Field(..., min_length=1, max_length=100)


class LabResultSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lab_order_id: uuid.UUID
    parameter: str
    value: str
    unit: str | None
    reference_range: str | None
    flag: str
    entered_by: uuid.UUID
    finalized_at: datetime | None
    created_at: datetime


class LabOrderSummary(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID | None
    test: LabTestSummary
    ordered_by: uuid.UUID
    status: str
    ordered_at: datetime
    sample_collected_at: datetime | None
    resulted_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_reason: str | None
    created_at: datetime
    updated_at: datetime
    results: list[LabResultSummary]


class LabOrderListResponse(BaseModel):
    items: list[LabOrderSummary]
    total: int
    limit: int
    offset: int
