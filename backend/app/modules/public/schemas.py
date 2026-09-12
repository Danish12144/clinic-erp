"""Request/response shapes for the public (unauthenticated) clinic
discovery + self-booking surface — Phase 2 (Master Handoff item 1).
Deliberately separate from `app.modules.appointments.schemas`/
`app.modules.doctors.schemas`: these are the PII-minimal, public-facing
projections a stranger who has never visited the clinic is allowed to
see, not the staff-facing shapes (no email/phone/registration_number for
doctors, no internal ids beyond what booking itself needs).
"""

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 \-]{6,17}$")
_PAST_GRACE = timedelta(minutes=5)


def _validate_phone(value: str) -> str:
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError("phone must be digits (optionally with a leading '+', spaces, or hyphens), 7-18 characters")
    return value


class PublicClinicSummary(BaseModel):
    slug: str
    name: str
    timezone: str


class PublicBranchSummary(BaseModel):
    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None


class PublicDoctorSummary(BaseModel):
    """Mirrors `DoctorDirectoryEntry` minus PII this surface has no
    business showing to an anonymous caller."""

    user_id: uuid.UUID
    first_name: str | None
    last_name: str | None
    specialization: str | None
    consultation_fee: Decimal | None
    slot_duration_minutes: int
    branch_ids: list[uuid.UUID]


class PublicSlot(BaseModel):
    scheduled_at: datetime
    duration_minutes: int


class PublicSlotsResponse(BaseModel):
    date: date
    slots: list[PublicSlot]


class PublicBookingRequest(BaseModel):
    branch_id: uuid.UUID
    doctor_id: uuid.UUID
    scheduled_at: datetime
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str = Field(..., description="Used to find-or-create the patient record and to verify ownership later")
    email: EmailStr | None = None
    # Real online prepayment is opt-in per booking, not mandatory — a
    # clinic that hasn't configured a payment gateway (payment_gateway_
    # provider still "mock"/unconfigured) can still take free bookings;
    # this only ever attempts a gateway order when explicitly requested.
    request_prepayment: bool = False
    prepayment_amount: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return _validate_phone(value)

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone offset (e.g. '2026-09-10T10:00:00+05:30')")
        if value <= datetime.now(timezone.utc) - _PAST_GRACE:
            raise ValueError("scheduled_at must be in the future")
        return value


class PublicGatewayOrderInfo(BaseModel):
    """Everything the frontend needs to open the gateway's own checkout
    widget (e.g. Razorpay Checkout.js) — never a secret; `key_id` is the
    gateway's public/publishable key, safe to expose client-side (the
    matching `key_secret` never leaves the backend)."""

    provider: str
    order_id: str
    amount: Decimal
    currency: str
    key_id: str


class PublicBookingResponse(BaseModel):
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    scheduled_at: datetime
    duration_minutes: int
    status: str
    payment_status: str
    gateway_order: PublicGatewayOrderInfo | None = None


class PublicRetryPaymentRequest(BaseModel):
    phone: str = Field(..., description="Must match the phone the booking was made with")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return _validate_phone(value)
