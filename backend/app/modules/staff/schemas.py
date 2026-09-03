import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.modules.auth.schemas import InviteInfo

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")

# Deliberately excludes OWNER (not provisioned via any staff-account flow —
# clinic onboarding is out of scope, PRD §30), DOCTOR (its own module), and
# PATIENT (not staff at all).
StaffRoleCode = Literal["RECEPTIONIST", "NURSE", "LAB_STAFF", "PHARMACY_STAFF", "OTHER_STAFF"]


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError("phone must be digits (optionally with a leading '+', spaces, or hyphens), 7-18 characters")
    return value


class StaffCreateRequest(BaseModel):
    role_code: StaffRoleCode
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = None
    employee_code: str | None = Field(None, max_length=50)
    designation: str | None = Field(None, max_length=200)
    joining_date: date | None = None
    branch_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @model_validator(mode="after")
    def require_email_or_phone(self) -> "StaffCreateRequest":
        if self.email is None and self.phone is None:
            raise ValueError("provide at least an email address or a phone number")
        return self


class StaffUpdateRequest(BaseModel):
    """`role_code` is deliberately not editable here — changing a staff
    member's role changes their whole permission set and is a bigger
    operation than a profile edit; not implemented in this module."""

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    employee_code: str | None = Field(None, max_length=50)
    designation: str | None = Field(None, max_length=200)
    joining_date: date | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "StaffUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class StaffSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role_code: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    status: str
    employee_code: str | None
    designation: str | None
    joining_date: date | None
    branch_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime


class StaffListResponse(BaseModel):
    items: list[StaffSummary]
    total: int
    limit: int
    offset: int


class BranchAssignmentRequest(BaseModel):
    branch_ids: list[uuid.UUID] = Field(default_factory=list)


class StaffCreateResponse(BaseModel):
    staff: StaffSummary
    invite: InviteInfo
