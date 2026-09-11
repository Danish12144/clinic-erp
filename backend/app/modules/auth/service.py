"""Auth module business logic: staff email/phone+password login, patient
phone+OTP login, refresh-token rotation, logout, and session listing. See
PRD-ARCHITECTURE.md §12 (authentication strategy) and §13 (RBAC).

Every public method resolves the tenant from a `clinic_slug` first (the
stand-in for subdomain-based resolution described in §11 — see
TenantResolutionRepository), then opens a tenant-scoped session for
everything else. Nothing here ever queries across tenants except that one
resolution step.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core import security
from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.auth.models import User, UserStatus
from app.modules.auth.otp_sender import OtpSender, get_otp_sender
from app.modules.auth.repository import (
    OtpRepository,
    PermissionOverrideRepository,
    PermissionRepository,
    RoleRepository,
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
    PermissionOverrideListResponse,
    PermissionOverrideSetRequest,
    PermissionOverrideSummary,
    SessionSummary,
    TokenResponse,
    UserSummary,
)
from app.modules.patients.repository import PatientRepository

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

    async def _resolve_or_provision_patient_user(self, session, *, tenant_id: uuid.UUID, phone: str) -> User | None:
        """Self-service portal account linking (PRD §9's "patient portal,"
        previously blocked entirely — `patients.user_id` has been
        schema-ready since the Patients module shipped, but nothing ever
        wrote to it). If a `User` already owns this phone, that's the
        normal returning-patient path (or a staff member's phone, handled
        below — never auto-provisioned over). Otherwise, exactly one
        not-yet-linked `Patient` sharing this phone is enough certainty to
        create the login and link it automatically; zero or more-than-one
        match stays ambiguous and falls through to the generic response,
        same as an unregistered phone — this never guesses."""
        user_repo = UserRepository(session)
        user = await user_repo.get_by_phone(phone)
        if user is not None:
            return user if user.role.code == "PATIENT" else None

        candidates = await PatientRepository(session).find_unlinked_by_phone(tenant_id=tenant_id, phone=phone)
        if len(candidates) != 1:
            return None
        patient = candidates[0]

        patient_role = await RoleRepository(session).get_by_code("PATIENT")
        if patient_role is None:
            return None
        new_user = await user_repo.create_patient_user(
            tenant_id=tenant_id, role_id=patient_role.id, phone=phone, first_name=patient.first_name, last_name=patient.last_name,
        )
        await PatientRepository(session).link_user(patient_id=patient.id, user_id=new_user.id)
        await record_audit(
            session, tenant_id=tenant_id, actor_user_id=new_user.id, actor_role="PATIENT",
            action="patient_user.self_provision", entity_type="patient", entity_id=patient.id, before=None,
            after={"user_id": str(new_user.id)},
        )
        return new_user

    async def request_patient_otp(self, *, clinic_slug: str, phone: str) -> OtpRequestResponse:
        tenant_id = await self._resolve_tenant_id(clinic_slug)
        generic_response = OtpRequestResponse(message="If this phone number is registered, an OTP has been sent.")

        async with tenant_session(tenant_id) as session:
            user = await self._resolve_or_provision_patient_user(session, tenant_id=tenant_id, phone=phone)
            # Same response whether or not the phone is registered — don't
            # let an unauthenticated caller enumerate accounts.
            if user is None:
                return generic_response

            code = settings.otp_static_code or security.generate_otp_code()
            otp_repo = OtpRepository(session)
            await otp_repo.create(
                tenant_id=tenant_id,
                user_id=user.id,
                code_hash=security.hash_otp_code(code),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes),
            )
            await self._otp_sender.send(phone=phone, code=code)

        # A static demo code has no secrecy to defeat by echoing it back —
        # see Settings.otp_static_code's own docstring — so it's revealed
        # even in production, unlike a real random code.
        reveal_code = settings.otp_static_code is not None or not settings.is_production
        if not reveal_code:
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


class PermissionOverrideService:
    """The write side of PRD §13's two-layer RBAC resolution — closes the
    gap flagged repeatedly across this session's module notes (first in
    Vitals'): the mechanism has been readable (`PermissionRepository.
    resolve_effective_permissions`, embedded in every JWT since migration
    0001) but had no endpoint to actually create/change an override until
    now. A revoked/granted override takes effect on the affected user's
    *next token refresh*, not instantly — same latency tradeoff PRD §13
    itself calls out, unchanged by this module.
    """

    async def set_override(self, *, tenant_id: uuid.UUID, payload: PermissionOverrideSetRequest, actor_user_id: uuid.UUID, actor_role: str) -> PermissionOverrideSummary:
        async with tenant_session(tenant_id) as session:
            permission = await PermissionRepository(session).get_by_code(payload.permission_code)
            if permission is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Permission '{payload.permission_code}' does not exist")

            override_repo = PermissionOverrideRepository(session)
            if payload.role_code is not None:
                role = await RoleRepository(session).get_by_code(payload.role_code)
                if role is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Role '{payload.role_code}' does not exist")
                before = await override_repo.get_for_role(tenant_id=tenant_id, role_id=role.id, permission_id=permission.id)
                before_granted = before.granted if before is not None else None
                override = await override_repo.upsert_for_role(
                    tenant_id=tenant_id, role_id=role.id, permission_id=permission.id, granted=payload.granted, created_by=actor_user_id,
                )
            else:
                assert payload.user_id is not None
                if await UserRepository(session).get_by_id(payload.user_id) is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"User '{payload.user_id}' does not exist")
                before = await override_repo.get_for_user(tenant_id=tenant_id, user_id=payload.user_id, permission_id=permission.id)
                before_granted = before.granted if before is not None else None
                override = await override_repo.upsert_for_user(
                    tenant_id=tenant_id, user_id=payload.user_id, permission_id=permission.id, granted=payload.granted, created_by=actor_user_id,
                )

            summary = PermissionOverrideSummary(
                id=override.id, tenant_id=tenant_id, role_code=payload.role_code, user_id=payload.user_id,
                permission_code=payload.permission_code, granted=override.granted, created_by=override.created_by,
                created_at=override.created_at, updated_at=override.updated_at,
            )
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="permission_override.set", entity_type="permission_override", entity_id=override.id,
                before={"granted": before_granted} if before_granted is not None else None,
                after=summary.model_dump(mode="json"),
            )
            return summary

    async def search_overrides(
        self, *, tenant_id: uuid.UUID, role_code: str | None, user_id: uuid.UUID | None, limit: int, offset: int,
    ) -> PermissionOverrideListResponse:
        async with tenant_session(tenant_id) as session:
            role_id = None
            if role_code is not None:
                role = await RoleRepository(session).get_by_code(role_code)
                if role is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Role '{role_code}' does not exist")
                role_id = role.id

            rows, total = await PermissionOverrideRepository(session).search(tenant_id=tenant_id, role_id=role_id, user_id=user_id, limit=limit, offset=offset)
            items = [
                PermissionOverrideSummary(
                    id=override.id, tenant_id=override.tenant_id, role_code=role_code_value, user_id=override.user_id,
                    permission_code=permission_code_value, granted=override.granted, created_by=override.created_by,
                    created_at=override.created_at, updated_at=override.updated_at,
                )
                for override, role_code_value, permission_code_value in rows
            ]
            return PermissionOverrideListResponse(items=items, total=total, limit=limit, offset=offset)

    async def delete_override(self, *, tenant_id: uuid.UUID, override_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> None:
        async with tenant_session(tenant_id) as session:
            repo = PermissionOverrideRepository(session)
            override = await repo.get_by_id(override_id)
            if override is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Permission override not found")
            await repo.delete(override_id)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="permission_override.delete", entity_type="permission_override", entity_id=override_id,
                before={"granted": override.granted}, after=None,
            )


async def issue_staff_invite(session, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
    """Called by Doctor/Staff Management from within their own already-open
    `tenant_session`, right after creating the `User` row for a new staff
    account (and again from either module's `resend_invite`) — hence
    taking `session` directly rather than opening one itself, unlike every
    method on `AuthService`.

    Branches by `settings.is_production`, and the two branches are
    genuinely different mechanisms, not the same one with a field hidden:

    - Outside production (dev/test — this is the ONLY path either
      environment ever takes, so every existing integration test's
      create-account-then-accept-invite setup helper is completely
      unaffected by the branch below): unchanged from before this
      docstring was rewritten — deletes any still-pending invite for the
      user first (so a resend invalidates the previous token rather than
      leaving two valid at once), creates a real `StaffInvite` row, and
      returns its raw token via `debug_invite_token` for `accept-invite`.
    - In production: there is still no real email/SMS provider wired up
      (`app/modules/notifications/adapters.py` — `ConsoleChannelAdapter`
      only), and `debug_invite_token` is deliberately `None` here in
      production regardless, so issuing an invite token nobody can ever
      receive would create an account that can never be activated. Instead,
      this generates a random password, activates the account with it
      immediately (`UserRepository.activate_with_password` — the exact
      same repository method `AuthService.accept_invite` already calls),
      and returns it once via `temporary_password` — the same one-time-
      reveal pattern `scripts/seed_clinic_owner.py` uses for the first
      Owner account. No `StaffInvite` row is created at all in this
      branch; there is nothing for it to represent."""
    if settings.is_production:
        raw_password = secrets.token_urlsafe(18)
        await UserRepository(session).activate_with_password(user_id, password_hash=security.hash_password(raw_password))
        return InviteInfo(temporary_password=raw_password)

    invite_repo = StaffInviteRepository(session)
    await invite_repo.delete_pending_for_user(user_id)
    token = security.generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.staff_invite_expire_hours)
    await invite_repo.create(
        tenant_id=tenant_id, user_id=user_id, token_hash=security.hash_opaque_token(token), expires_at=expires_at
    )
    return InviteInfo(invite_expires_at=expires_at, debug_invite_token=token)
