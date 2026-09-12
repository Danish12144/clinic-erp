import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.auth.schemas import InviteInfo
from app.modules.tenancy.schemas import WorkingHours

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")


def _default_doctor_working_hours() -> WorkingHours:
    """A newly invited doctor gets sensible regular OPD hours (Mon-Sat
    09:00-18:00) instead of WorkingHours()'s own fail-closed empty default
    — matching scripts/seed_demo_accounts.py's DOCTOR_WORKING_HOURS, so
    every doctor (not just demo-seeded ones) is actually bookable out of
    the box. A caller that supplies its own `working_hours` in the request
    body still overrides this, unchanged."""
    open_close = {"open": "09:00", "close": "18:00"}
    return WorkingHours.model_validate({day: open_close for day in ("mon", "tue", "wed", "thu", "fri", "sat")})


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError("phone must be digits (optionally with a leading '+', spaces, or hyphens), 7-18 characters")
    return value


class DoctorCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = None
    specialization: str | None = Field(None, max_length=200)
    registration_number: str | None = Field(None, max_length=100)
    consultation_fee: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    working_hours: WorkingHours = Field(default_factory=_default_doctor_working_hours)
    # Phase 1 (migration 0033) — matches doctor_profiles' own DB CHECK
    # (5-240) and the frontend Appointments page's existing 5-240 range for
    # a single appointment's duration_minutes, so the two concepts share
    # one sensible bound even though they're otherwise independent.
    slot_duration_minutes: int = Field(15, ge=5, le=240)
    bio: str | None = Field(None, max_length=2000)
    branch_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @model_validator(mode="after")
    def require_email_or_phone(self) -> "DoctorCreateRequest":
        if self.email is None and self.phone is None:
            raise ValueError("provide at least an email address or a phone number")
        return self


class DoctorUpdateRequest(BaseModel):
    """Shared by both the Owner "update any doctor" endpoint and the
    Doctor "update my own profile" endpoint (PRD §3: Owner has full access,
    Doctor has full access to their own record only — same field set
    either way). Branch assignment is deliberately not here — see the
    dedicated `/branches` endpoint, an Owner-only administrative action."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    specialization: str | None = Field(None, max_length=200)
    registration_number: str | None = Field(None, max_length=100)
    consultation_fee: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=2)
    working_hours: WorkingHours | None = None
    slot_duration_minutes: int | None = Field(None, ge=5, le=240)
    bio: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "DoctorUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class DoctorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    status: str
    specialization: str | None
    registration_number: str | None
    consultation_fee: Decimal | None
    working_hours: dict
    slot_duration_minutes: int
    bio: str | None
    branch_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class DoctorListResponse(BaseModel):
    items: list[DoctorSummary]
    total: int
    limit: int
    offset: int


class BranchAssignmentRequest(BaseModel):
    branch_ids: list[uuid.UUID] = Field(default_factory=list)


class DoctorCreateResponse(BaseModel):
    doctor: DoctorSummary
    invite: InviteInfo


class DoctorDirectoryEntry(BaseModel):
    """The public-facing subset of a doctor's data — deliberately NOT
    `DoctorSummary`: no `email`/`phone`/`registration_number`/`status`.
    Used by `GET /api/v1/doctors/directory` (Receptionist/Patient, for
    booking flows), which only lists ACTIVE doctors in the first place —
    see DoctorRepository.search_directory."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    first_name: str | None
    last_name: str | None
    specialization: str | None
    consultation_fee: Decimal | None
    working_hours: dict
    slot_duration_minutes: int
    branch_ids: list[uuid.UUID]


class DoctorDirectoryResponse(BaseModel):
    items: list[DoctorDirectoryEntry]
    total: int
    limit: int
    offset: int
