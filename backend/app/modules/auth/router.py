import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.modules.auth.schemas import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    AccessTokenOnlyResponse,
    LogoutRequest,
    MeResponse,
    OtpRequestPayload,
    OtpRequestResponse,
    OtpVerifyPayload,
    PermissionOverrideListResponse,
    PermissionOverrideSetRequest,
    PermissionOverrideSummary,
    RefreshRequest,
    SessionSummary,
    StaffLoginRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService, PermissionOverrideService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
permission_override_router = APIRouter(prefix="/api/v1/permission-overrides", tags=["auth"])


def get_auth_service() -> AuthService:
    return AuthService()


def get_permission_override_service() -> PermissionOverrideService:
    return PermissionOverrideService()


@router.post("/staff/login", response_model=TokenResponse)
async def staff_login(
    payload: StaffLoginRequest, request: Request, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return await service.staff_login(
        clinic_slug=payload.clinic_slug,
        identifier=payload.identifier,
        password=payload.password,
        device_label=request.headers.get("x-device-label"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/staff/refresh", response_model=AccessTokenOnlyResponse)
async def staff_refresh(
    payload: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> AccessTokenOnlyResponse:
    return await service.refresh(clinic_slug=payload.clinic_slug, refresh_token=payload.refresh_token)


@router.post("/staff/logout", status_code=status.HTTP_204_NO_CONTENT)
async def staff_logout(payload: LogoutRequest, service: AuthService = Depends(get_auth_service)) -> None:
    await service.logout(clinic_slug=payload.clinic_slug, refresh_token=payload.refresh_token)


@router.post("/patient/otp/request", response_model=OtpRequestResponse)
async def request_patient_otp(
    payload: OtpRequestPayload, service: AuthService = Depends(get_auth_service)
) -> OtpRequestResponse:
    return await service.request_patient_otp(clinic_slug=payload.clinic_slug, phone=payload.phone)


@router.post("/patient/otp/verify", response_model=TokenResponse)
async def verify_patient_otp(
    payload: OtpVerifyPayload, request: Request, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    return await service.verify_patient_otp(
        clinic_slug=payload.clinic_slug,
        phone=payload.phone,
        code=payload.code,
        device_label=request.headers.get("x-device-label"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/accept-invite", response_model=AcceptInviteResponse)
async def accept_invite(
    payload: AcceptInviteRequest, service: AuthService = Depends(get_auth_service)
) -> AcceptInviteResponse:
    """Activates a staff account provisioned by Doctor or Staff Management
    (see app/modules/auth/service.py::issue_staff_invite) — role-agnostic,
    unauthenticated (the invited user has no credentials yet)."""
    return await service.accept_invite(clinic_slug=payload.clinic_slug, token=payload.token, password=payload.password)


@router.get("/me", response_model=MeResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user), service: AuthService = Depends(get_auth_service)
) -> MeResponse:
    user_summary = await service.get_profile(tenant_id=current_user.tenant_id, user_id=current_user.user_id)
    return MeResponse(user=user_summary, permissions=sorted(current_user.permissions))


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    current_user: CurrentUser = Depends(get_current_user), service: AuthService = Depends(get_auth_service)
) -> list[SessionSummary]:
    return await service.list_sessions(tenant_id=current_user.tenant_id, user_id=current_user.user_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.revoke_session(tenant_id=current_user.tenant_id, user_id=current_user.user_id, session_id=session_id)


# ---- Permission overrides (PRD §13's write side) -------------------------------
#
# `staff.manage` (Owner-only, per the PRD §3 matrix's "Staff, roles &
# permissions" row) gates every route here — the same permission that
# already gates Staff/Doctor Management's own role-assignment endpoints.


@permission_override_router.put("", response_model=PermissionOverrideSummary)
async def set_permission_override(
    payload: PermissionOverrideSetRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: PermissionOverrideService = Depends(get_permission_override_service),
) -> PermissionOverrideSummary:
    return await service.set_override(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@permission_override_router.get("", response_model=PermissionOverrideListResponse)
async def search_permission_overrides(
    role_code: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: PermissionOverrideService = Depends(get_permission_override_service),
) -> PermissionOverrideListResponse:
    return await service.search_overrides(tenant_id=current_user.tenant_id, role_code=role_code, user_id=user_id, limit=limit, offset=offset)


@permission_override_router.delete("/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission_override(
    override_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: PermissionOverrideService = Depends(get_permission_override_service),
) -> None:
    await service.delete_override(tenant_id=current_user.tenant_id, override_id=override_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
