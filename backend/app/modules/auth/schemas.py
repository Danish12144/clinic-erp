import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StaffLoginRequest(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    identifier: str = Field(..., min_length=1, description="Staff email or phone number")
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    refresh_token: str = Field(..., min_length=1)


class OtpRequestPayload(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=6, max_length=20)


class OtpVerifyPayload(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=6, max_length=20)
    code: str = Field(..., min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def code_must_be_numeric(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP code must be a 6-digit number")
        return value


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    first_name: str | None
    last_name: str | None
    email: str | None
    phone: str | None
    role_code: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserSummary


class AccessTokenOnlyResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class OtpRequestResponse(BaseModel):
    message: str
    # Only populated outside `production` (Settings.environment) — lets
    # local dev / integration tests complete the OTP flow without a real
    # SMS provider. See app/modules/auth/otp_sender.py.
    debug_code: str | None = None


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_label: str | None
    ip_address: str | None
    issued_at: datetime
    expires_at: datetime


class MeResponse(BaseModel):
    user: UserSummary
    permissions: list[str]
