import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class InviteInfo(BaseModel):
    """Returned by both Doctor and Staff Management's create/resend-invite
    endpoints — the invite mechanism itself lives here in Auth (see
    StaffInvite), shared by any module that provisions a staff account."""

    invite_expires_at: datetime
    # Only populated outside `production` — same placeholder-delivery
    # pattern as OTP's `debug_code` above, until a real Communications
    # module can deliver this via email/SMS.
    debug_invite_token: str | None = None


class AcceptInviteRequest(BaseModel):
    clinic_slug: str = Field(..., min_length=1, max_length=100)
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class AcceptInviteResponse(BaseModel):
    message: str


# ---- Permission overrides (PRD §13's write side) -------------------------------


class PermissionOverrideSetRequest(BaseModel):
    """Exactly one of `role_code`/`user_id` must be supplied — matches the
    DB `CHECK` on `permission_overrides` (a role-wide override or a single
    staff member's override, never both, never neither). `PUT` semantics:
    calling this again for the same target+permission replaces the prior
    `granted` value rather than erroring or duplicating."""

    role_code: str | None = Field(None, description='e.g. "RECEPTIONIST" — one of the 8 system role codes')
    user_id: uuid.UUID | None = None
    permission_code: str = Field(..., min_length=1, description='e.g. "vitals.record"')
    granted: bool

    @model_validator(mode="after")
    def exactly_one_target(self) -> "PermissionOverrideSetRequest":
        if (self.role_code is not None) == (self.user_id is not None):
            raise ValueError("provide exactly one of role_code or user_id")
        return self


class PermissionOverrideSummary(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    role_code: str | None
    user_id: uuid.UUID | None
    permission_code: str
    granted: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PermissionOverrideListResponse(BaseModel):
    items: list[PermissionOverrideSummary]
    total: int
    limit: int
    offset: int
