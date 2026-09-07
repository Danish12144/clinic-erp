import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.leads.models import LeadInteractionType, LeadSource, LeadStatus

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError("phone must be digits (optionally with a leading '+', spaces, or hyphens), 7-18 characters")
    return value


class LeadCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = None
    email: EmailStr | None = None
    source: LeadSource | None = None
    assigned_to_user_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)


class LeadUpdateRequest(BaseModel):
    """Status/assignment/notes, per this task's own wording — plus the
    contact fields any inbound-inquiry record might need correcting.
    `status` here can never be set to `CONVERTED`: that transition is only
    reachable through `POST .../convert`, which is what actually creates
    the linked `Patient` — see `LeadService.update_lead`."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = None
    email: EmailStr | None = None
    source: LeadSource | None = None
    status: LeadStatus | None = None
    assigned_to_user_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "LeadUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class LeadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str
    last_name: str | None
    phone: str | None
    email: str | None
    source: LeadSource | None
    status: LeadStatus
    assigned_to_user_id: uuid.UUID | None
    notes: str | None
    converted_patient_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadSummary]
    total: int
    limit: int
    offset: int


# ---- Interactions -------------------------------------------------------------


class LeadInteractionCreateRequest(BaseModel):
    interaction_type: LeadInteractionType
    outcome: str | None = Field(None, max_length=300)
    notes: str | None = Field(None, max_length=2000)


class LeadInteractionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    lead_id: uuid.UUID
    interaction_type: LeadInteractionType
    outcome: str | None
    notes: str | None
    performed_by: uuid.UUID
    created_at: datetime


# ---- Conversion ---------------------------------------------------------------


Gender = Literal["Male", "Female", "Other"]


class LeadConvertRequest(BaseModel):
    """Everything is optional — by default the new `Patient` is built
    straight from the lead's own `first_name`/`last_name`/`phone`/`email`.
    These fields exist only to fill in clinically-relevant data Leads never
    captures, not to rename/correct contact details already on the lead
    (use `PATCH /leads/{id}` for that, before converting)."""

    gender: Gender | None = None
    date_of_birth: date | None = None
    address: str | None = Field(None, max_length=500)


class LeadConvertResponse(BaseModel):
    lead: LeadSummary
    patient_id: uuid.UUID
