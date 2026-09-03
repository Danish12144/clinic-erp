import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_future(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("scheduled_at must include a timezone offset (e.g. '2026-09-10T10:00:00+05:30')")
    if value <= datetime.now(timezone.utc):
        raise ValueError("scheduled_at must be in the future")
    return value


class AppointmentCreateRequest(BaseModel):
    """Used by the Owner/Receptionist "book for any patient" endpoint —
    `patient_id` is required. See `MyAppointmentCreateRequest` for the
    patient self-booking variant, where it's derived from the caller."""

    patient_id: uuid.UUID
    branch_id: uuid.UUID
    doctor_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(15, ge=5, le=240)
    notes: str | None = Field(None, max_length=1000)

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime) -> datetime:
        return _validate_future(value)


class MyAppointmentCreateRequest(BaseModel):
    branch_id: uuid.UUID
    doctor_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int = Field(15, ge=5, le=240)
    notes: str | None = Field(None, max_length=1000)

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime) -> datetime:
        return _validate_future(value)


class AppointmentRescheduleRequest(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(None, ge=5, le=240)
    doctor_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=1000)

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_future(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "AppointmentRescheduleRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class AppointmentCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class AppointmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID | None
    source: str
    scheduled_at: datetime
    duration_minutes: int
    status: str
    notes: str | None
    cancelled_reason: str | None
    cancelled_by: uuid.UUID | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AppointmentListResponse(BaseModel):
    items: list[AppointmentSummary]
    total: int
    limit: int
    offset: int
