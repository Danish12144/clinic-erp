import re
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

Gender = Literal["Male", "Female", "Other"]
BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")
_MRN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{2,49}$")
_MAX_LIST_ITEMS = 50
_MAX_LIST_ITEM_LENGTH = 200


def _validate_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError("phone must be digits (optionally with a leading '+', spaces, or hyphens), 7-18 characters")
    return value


def _validate_dob(value: date | None) -> date | None:
    if value is None:
        return None
    if value > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    if value < date.today() - timedelta(days=130 * 365):
        raise ValueError("date_of_birth is implausibly far in the past")
    return value


def _validate_string_list(values: list[str], *, field_name: str) -> list[str]:
    if len(values) > _MAX_LIST_ITEMS:
        raise ValueError(f"{field_name} cannot have more than {_MAX_LIST_ITEMS} entries")
    cleaned = [v.strip() for v in values if v.strip()]
    for item in cleaned:
        if len(item) > _MAX_LIST_ITEM_LENGTH:
            raise ValueError(f"each {field_name} entry must be at most {_MAX_LIST_ITEM_LENGTH} characters")
    return cleaned


class EmergencyContact(BaseModel):
    """All three fields are required together — an emergency contact with
    a name but no way to reach them isn't useful, so it's all-or-nothing
    rather than allowing a half-filled-in contact."""

    name: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., min_length=1)
    relationship: str = Field(..., min_length=1, max_length=100)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        validated = _validate_phone(value)
        assert validated is not None
        return validated


class PatientCreateRequest(BaseModel):
    mrn: str | None = Field(None, description="Auto-generated if omitted")
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    gender: Gender | None = None
    date_of_birth: date | None = None
    phone: str | None = None
    email: EmailStr | None = None
    blood_group: BloodGroup | None = None
    allergies: list[str] = Field(default_factory=list)
    chronic_conditions: list[str] = Field(default_factory=list)
    emergency_contact: EmergencyContact | None = None
    address: str | None = Field(None, max_length=500)

    @field_validator("mrn")
    @classmethod
    def validate_mrn(cls, value: str | None) -> str | None:
        if value is not None and not _MRN_PATTERN.match(value):
            raise ValueError("mrn must be 3-50 alphanumeric characters (hyphens allowed), no whitespace")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date | None) -> date | None:
        return _validate_dob(value)

    @field_validator("allergies")
    @classmethod
    def validate_allergies(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value, field_name="allergies")

    @field_validator("chronic_conditions")
    @classmethod
    def validate_chronic_conditions(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value, field_name="chronic_conditions")

    @model_validator(mode="after")
    def require_some_contact_detail(self) -> "PatientCreateRequest":
        # Not enforced at the DB level (both columns are nullable, per the
        # master schema — a walk-in might decline to share either), but a
        # patient record with neither is very unlikely to be searchable or
        # useful later. Soft product guardrail, not a hard data constraint.
        if self.phone is None and self.email is None:
            raise ValueError("provide at least a phone number or an email address")
        return self


class PatientUpdateRequest(BaseModel):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    gender: Gender | None = None
    date_of_birth: date | None = None
    phone: str | None = None
    email: EmailStr | None = None
    blood_group: BloodGroup | None = None
    allergies: list[str] | None = None
    chronic_conditions: list[str] | None = None
    emergency_contact: EmergencyContact | None = None
    address: str | None = Field(None, max_length=500)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @field_validator("date_of_birth")
    @classmethod
    def validate_dob(cls, value: date | None) -> date | None:
        return _validate_dob(value)

    @field_validator("allergies")
    @classmethod
    def validate_allergies(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_string_list(value, field_name="allergies")

    @field_validator("chronic_conditions")
    @classmethod
    def validate_chronic_conditions(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_string_list(value, field_name="chronic_conditions")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "PatientUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class PatientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    mrn: str
    first_name: str
    last_name: str | None
    gender: str | None
    date_of_birth: date | None
    phone: str | None
    email: str | None
    blood_group: str | None
    allergies: list[str]
    chronic_conditions: list[str]
    emergency_contact: dict | None
    address: str | None
    created_at: datetime
    updated_at: datetime


class PatientCreateResponse(BaseModel):
    patient: PatientSummary
    possible_duplicates: list[PatientSummary] = Field(
        default_factory=list,
        description=(
            "Existing patients that share this phone number, or share both name and date of birth. "
            "A soft warning only — the new record is always created; PRD-ARCHITECTURE.md §5.1 requires "
            "duplicate merging to stay a manual, audited action, never automatic."
        ),
    )


class PatientListResponse(BaseModel):
    items: list[PatientSummary]
    total: int
    limit: int
    offset: int
