"""Auth module business logic: staff email/phone+password login, patient
phone+OTP login, refresh-token rotation, logout, and session listing. See
PRD-ARCHITECTURE.md §12 (authentication strategy) and §13 (RBAC).

Every public method resolves the tenant from a `clinic_slug` first (the
stand-in for subdomain-based resolution described in §11 — see
TenantResolutionRepository), then opens a tenant-scoped session for
everything else. Nothing here ever queries across tenants except that one
resolution step.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core import security
from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.auth.models import User, UserStatus
from app.modules.auth.otp_sender import OtpSender, get_otp_sender
from app.modules.auth.repository import (
    OtpRepository,
    PermissionRepository,
    SessionRepository,
    StaffInviteRepository,
    TenantResolutionRepository,
    UserRepository,
)
from app.modules.auth.schemas import (
    AcceptInviteResponse,
    AccessTokenOnlyResponse,
    InviteInfo,
    OtpRequestResponse,
    SessionSummary,
    TokenResponse,
    UserSummary,
)

settings = get_settings()


class AuthService:
    def __init__(self, otp_sender: OtpSender | None = None) -> None:
        self._otp_sender = otp_sender or get_otp_sender()

    async def _resolve_tenant_id(self, clinic_slug: str) -> uuid.UUID:
        clinic = await TenantResolutionRepository.get_active_clinic_by_slug(clinic_slug)
        if clinic is None:
            # Same message for "no such clinic" and "clinic suspended" —
            # no reason to help an unauthenticated caller distinguish them.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
        return clinic.id

    # ---- Staff (email/phone + password) --------------------------------

    async def staff_login(
        self,
        *,
        clinic_slug: str,
        identifier: str,
        password: str,
        device_label: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)

        async with tenant_session(tenant_id) as session:
            user_repo = UserRepository(session)
            is_email = "@" in identifier
            user = await (user_repo.get_by_email(identifier) if is_email else user_repo.get_by_phone(identifier))

            if user is None or user.password_hash is None or not security.verify_password(password, user.password_hash):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
            if user.status != UserStatus.ACTIVE:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")

            return await self._issue_tokens(session, user, device_label, ip_address, user_agent)

    # ---- Patient (phone + OTP) ------------------------------------------

    async def request_patient_otp(self, *, clinic_slug: str, phone: str) -> OtpRequestResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        generic_response = OtpRequestResponse(message="If this phone number is registered, an OTP has been sent.")

        async with tenant_session(tenant_id) as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_phone(phone)
            # Same response whether or not the phone is registered — don't
            # let an unauthenticated caller enumerate accounts.
            if user is None or user.role.code != "PATIENT":
                return generic_response

            code = security.generate_otp_code()
            otp_repo = OtpRepository(session)
            await otp_repo.create(
                tenant_id=tenant_id,
                user_id=user.id,
                code_hash=security.hash_otp_code(code),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes),
            )
            await self._otp_sender.send(phone=phone, code=code)

        if settings.is_production:
            return generic_response
        return OtpRequestResponse(message=generic_response.message, debug_code=code)

    async def verify_patient_otp(
        self,
        *,
        clinic_slug: str,
        phone: str,
        code: str,
        device_label: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> TokenResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        invalid_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code")

        async with tenant_session(tenant_id) as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_phone(phone)
            if user is None or user.role.code != "PATIENT":
                raise invalid_error

            otp_repo = OtpRepository(session)
            otp = await otp_repo.get_latest_active(user_id=user.id)
            if otp is None or otp.expires_at < datetime.now(timezone.utc):
                raise invalid_error
            if otp.attempt_count >= settings.otp_max_attempts:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts — request a new code")
            if security.hash_otp_code(code) != otp.code_hash:
                await otp_repo.increment_attempts(otp.id)
                raise invalid_error

            await otp_repo.mark_consumed(otp.id)
            return await self._issue_tokens(session, user, device_label, ip_address, user_agent)

    # ---- Staff invite acceptance -----------------------------------------
    #
    # Issuance (`issue_staff_invite`, a free function below, not a method)
    # is called by Doctor/Staff Management from within their own already-open
    # tenant_session when they provision a new staff account — it doesn't
    # need AuthService's own session-per-call pattern. Acceptance is the
    # part that's genuinely pre-authentication (the invited user has no
    # credentials yet), so it belongs to AuthService alongside staff_login/
    # verify_patient_otp.

    async def accept_invite(self, *, clinic_slug: str, token: str, password: str) -> AcceptInviteResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        invalid_error = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invite")

        async with tenant_session(tenant_id) as session:
            invite_repo = StaffInviteRepository(session)
            invite = await invite_repo.get_active_by_token_hash(security.hash_opaque_token(token))
            if invite is None or invite.expires_at < datetime.now(timezone.utc):
                raise invalid_error

            await UserRepository(session).activate_with_password(invite.user_id, password_hash=security.hash_password(password))
            await invite_repo.mark_accepted(invite.id)
            return AcceptInviteResponse(message="Invite accepted — you can now log in with your new password")

    # ---- Shared token issuance / refresh / logout ------------------------

    async def _issue_tokens(self, session, user: User, device_label, ip_address, user_agent) -> TokenResponse:
        permission_repo = PermissionRepository(session)
        permissions = await permission_repo.resolve_effective_permissions(role_id=user.role_id, user_id=user.id)

        access_token = security.create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role_code=user.role.code, permissions=permissions
        )

        raw_refresh = security.generate_opaque_token()
        session_repo = SessionRepository(session)
        await session_repo.create(
            tenant_id=user.tenant_id,
            user_id=user.id,
            refresh_token_hash=security.hash_opaque_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
            device_label=device_label,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        user_repo = UserRepository(session)
        await user_repo.touch_last_login(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            user=UserSummary(
                id=user.id,
                tenant_id=user.tenant_id,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone=user.phone,
                role_code=user.role.code,
                status=user.status.value,
            ),
        )

    async def refresh(self, *, clinic_slug: str, refresh_token: str) -> AccessTokenOnlyResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        token_hash = security.hash_opaque_token(refresh_token)
        invalid_error = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

        async with tenant_session(tenant_id) as session:
            session_repo = SessionRepository(session)
            record = await session_repo.get_active_by_hash(token_hash)
            if record is None or record.expires_at < datetime.now(timezone.utc):
                raise invalid_error

            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(record.user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")

            # Rotate: revoke the presented refresh token and issue a new
            # one, so a leaked/replayed refresh token can't be reused
            # indefinitely.
            await session_repo.revoke(record.id)

            permission_repo = PermissionRepository(session)
            permissions = await permission_repo.resolve_effective_permissions(role_id=user.role_id, user_id=user.id)
            access_token = security.create_access_token(
                user_id=user.id, tenant_id=user.tenant_id, role_code=user.role.code, permissions=permissions
            )

            raw_refresh = security.generate_opaque_token()
            await session_repo.create(
                tenant_id=user.tenant_id,
                user_id=user.id,
                refresh_token_hash=security.hash_opaque_token(raw_refresh),
                expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
                device_label=record.device_label,
                ip_address=record.ip_address,
                user_agent=record.user_agent,
            )

            return AccessTokenOnlyResponse(access_token=access_token, refresh_token=raw_refresh)

    async def logout(self, *, clinic_slug: str, refresh_token: str) -> None:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        token_hash = security.hash_opaque_token(refresh_token)

        async with tenant_session(tenant_id) as session:
            session_repo = SessionRepository(session)
            record = await session_repo.get_active_by_hash(token_hash)
            if record is not None:
                await session_repo.revoke(record.id)

    # ---- Authenticated profile / session management ---------------------

    async def get_profile(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> UserSummary:
        async with tenant_session(tenant_id) as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_id(user_id)
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
            return UserSummary(
                id=user.id,
                tenant_id=user.tenant_id,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone=user.phone,
                role_code=user.role.code,
                status=user.status.value,
            )

    async def list_sessions(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[SessionSummary]:
        async with tenant_session(tenant_id) as session:
            session_repo = SessionRepository(session)
            records = await session_repo.list_active_for_user(user_id)
            return [SessionSummary.model_validate(record) for record in records]

    async def revoke_session(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        async with tenant_session(tenant_id) as session:
            session_repo = SessionRepository(session)
            # Scoped to the caller's own sessions by construction — a user
            # can only revoke a session that is also theirs. An owner
            # revoking a *different* staff member's session is a Staff
            # Management concern (needs that module's authorization model),
            # not implemented here.
            record = await session_repo.get_by_id_for_user(session_id, user_id)
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
            await session_repo.revoke(record.id)


async def issue_staff_invite(session, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
    """Called by Doctor/Staff Management from within their own already-open
    `tenant_session`, right after creating the `User` row for a new staff
    account — hence taking `session` directly rather than opening one
    itself, unlike every method on `AuthService`. Deletes any still-pending
    invite for the user first, so a resend invalidates the previous token
    rather than leaving two valid at once."""
    invite_repo = StaffInviteRepository(session)
    await invite_repo.delete_pending_for_user(user_id)
    token = security.generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.staff_invite_expire_hours)
    await invite_repo.create(
        tenant_id=tenant_id, user_id=user_id, token_hash=security.hash_opaque_token(token), expires_at=expires_at
    )
    return InviteInfo(invite_expires_at=expires_at, debug_invite_token=None if settings.is_production else token)
