import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

_READING_FIELDS = ("systolic_bp", "diastolic_bp", "heart_rate", "temperature_celsius", "spo2", "weight_kg", "height_cm")


class VitalsCreateRequest(BaseModel):
    """`patient_id`/`recorded_by` are deliberately not client-supplied
    fields — the service derives `patient_id` from the encounter (so a
    caller can't record a reading against a mismatched patient) and
    `recorded_by`/`recorded_by_role` from the authenticated caller."""

    encounter_id: uuid.UUID
    systolic_bp: int | None = Field(None, ge=40, le=300)
    diastolic_bp: int | None = Field(None, ge=20, le=200)
    heart_rate: int | None = Field(None, ge=20, le=300)
    temperature_celsius: float | None = Field(None, ge=30.0, le=45.0)
    spo2: int | None = Field(None, ge=0, le=100)
    weight_kg: float | None = Field(None, gt=0, le=500)
    height_cm: float | None = Field(None, gt=0, le=300)
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def at_least_one_reading(self) -> "VitalsCreateRequest":
        if all(getattr(self, field) is None for field in _READING_FIELDS):
            raise ValueError("at least one vitals reading field must be provided")
        return self


class VitalsSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    recorded_by: uuid.UUID
    recorded_by_role: str
    recorded_at: datetime
    systolic_bp: int | None
    diastolic_bp: int | None
    heart_rate: int | None
    temperature_celsius: float | None
    spo2: int | None
    weight_kg: float | None
    height_cm: float | None
    bmi: float | None
    notes: str | None
    created_at: datetime


class VitalsListResponse(BaseModel):
    items: list[VitalsSummary]
    total: int
    limit: int
    offset: int
