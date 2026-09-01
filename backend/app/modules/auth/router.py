import uuid

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentUser, get_current_user
from app.modules.auth.schemas import (
    AccessTokenOnlyResponse,
    LogoutRequest,
    MeResponse,
    OtpRequestPayload,
    OtpRequestResponse,
    OtpVerifyPayload,
    RefreshRequest,
    SessionSummary,
    StaffLoginRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_auth_service() -> AuthService:
    return AuthService()


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
