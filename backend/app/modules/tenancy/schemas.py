import re
import uuid
from datetime import datetime, time
from typing import Any
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_VALID_TIMEZONES = available_timezones()
_LOCALE_PATTERN = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
# GSTIN: 2-digit state code, 10-char PAN, 1 entity code digit, 'Z', 1 checksum char.
_GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _validate_timezone(value: str | None) -> str | None:
    if value is not None and value not in _VALID_TIMEZONES:
        raise ValueError(f"'{value}' is not a recognized IANA timezone (e.g. 'Asia/Kolkata')")
    return value


class DayHours(BaseModel):
    open: str = Field(..., description="24h HH:MM, e.g. '09:00'")
    close: str = Field(..., description="24h HH:MM, e.g. '18:00'")

    @field_validator("open", "close")
    @classmethod
    def valid_time_format(cls, value: str) -> str:
        if not _HHMM_PATTERN.match(value):
            raise ValueError("time must be in 24h HH:MM format, e.g. '09:00'")
        return value

    @model_validator(mode="after")
    def close_after_open(self) -> "DayHours":
        open_t = time.fromisoformat(self.open)
        close_t = time.fromisoformat(self.close)
        if close_t <= open_t:
            raise ValueError("'close' must be after 'open'")
        return self


class WorkingHours(BaseModel):
    """A day-code (mon..sun) -> DayHours map. Any day omitted is treated as
    closed. Not every clinic will set this at all — it's optional
    everywhere it's used."""

    model_config = ConfigDict(extra="forbid")

    mon: DayHours | None = None
    tue: DayHours | None = None
    wed: DayHours | None = None
    thu: DayHours | None = None
    fri: DayHours | None = None
    sat: DayHours | None = None
    sun: DayHours | None = None


# ---- Clinic -------------------------------------------------------------


class ClinicSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    locale: str
    gst_number: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ClinicUpdateRequest(BaseModel):
    """Deliberately excludes `slug` (tied to login/subdomain resolution —
    changing it is a distinct, carefully-handled operation not implemented
    here) and `status` (a Platform Admin / billing-lifecycle concern, e.g.
    suspending a non-paying tenant — no Platform Admin auth exists yet)."""

    name: str | None = Field(None, min_length=1, max_length=200)
    timezone: str | None = None
    locale: str | None = None
    gst_number: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is not None and not _LOCALE_PATTERN.match(value):
            raise ValueError("locale must be in 'xx-XX' format, e.g. 'en-IN'")
        return value

    @field_validator("gst_number")
    @classmethod
    def validate_gst_number(cls, value: str | None) -> str | None:
        if value is not None and value != "" and not _GSTIN_PATTERN.match(value):
            raise ValueError("gst_number does not look like a valid 15-character GSTIN")
        return value or None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ClinicUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


# ---- Branch ---------------------------------------------------------------


class BranchCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=30)
    timezone: str | None = None
    working_hours: WorkingHours = Field(default_factory=WorkingHours)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)


class BranchUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=30)
    timezone: str | None = None
    working_hours: WorkingHours | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BranchUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class BranchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    timezone: str | None
    working_hours: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---- Tenant settings --------------------------------------------------------

_SETTING_KEY_PATTERN = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+)*$")


class TenantSettingUpsertRequest(BaseModel):
    value: Any


class TenantSettingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    created_at: datetime
    updated_at: datetime


def validate_setting_key(key: str) -> str:
    """Shared by the router's path-parameter validation — a Pydantic
    field validator can't apply to a path param, so this is called
    directly. Keys are namespaced with dots, e.g. 'branding.primary_color',
    lowercase alnum/underscore segments only."""
    if not _SETTING_KEY_PATTERN.match(key):
        raise ValueError(
            "setting key must be lowercase dot-separated segments of letters/digits/underscores, "
            "e.g. 'branding.primary_color'"
        )
    return key
