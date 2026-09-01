import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import platform_admin_session
from app.modules.auth.models import OtpCode, Permission, PermissionOverride, RolePermission, User, UserSession
from app.modules.tenancy.models import Clinic


class TenantResolutionRepository:
    """The one legitimate pre-authentication, cross-tenant read in the
    system: turning a clinic slug into a tenant id so the rest of a login
    flow can open a properly tenant-scoped session. See
    app/core/db.py::platform_admin_session for why this needs the bypass —
    RLS on `clinics` requires knowing the tenant id already, which is
    exactly what this lookup exists to produce."""

    @staticmethod
    async def get_active_clinic_by_slug(slug: str) -> Clinic | None:
        async with platform_admin_session() as session:
            result = await session.execute(select(Clinic).where(Clinic.slug == slug))
            clinic = result.scalar_one_or_none()
            if clinic is None or clinic.status.value not in ("TRIAL", "ACTIVE"):
                return None
            return clinic


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        # Matches the DB's case-insensitive unique index
        # (ux_users_tenant_email is on lower(email)) on both sides.
        result = await self._session.execute(select(User).where(func.lower(User.email) == email.lower()))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone: str) -> User | None:
        result = await self._session.execute(select(User).where(User.phone == phone))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def touch_last_login(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(last_login_at=datetime.now(timezone.utc))
        )


class PermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_effective_permissions(self, *, role_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
        """PRD §13's two-layer resolution: role defaults, then role-level
        overrides, then user-level overrides — each layer able to add or
        remove a permission, later layers winning."""
        default_result = await self._session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        effective: set[str] = set(default_result.scalars().all())

        role_override_result = await self._session.execute(
            select(Permission.code, PermissionOverride.granted)
            .join(PermissionOverride, PermissionOverride.permission_id == Permission.id)
            .where(PermissionOverride.role_id == role_id)
        )
        for code, granted in role_override_result.all():
            (effective.add if granted else effective.discard)(code)

        user_override_result = await self._session.execute(
            select(Permission.code, PermissionOverride.granted)
            .join(PermissionOverride, PermissionOverride.permission_id == Permission.id)
            .where(PermissionOverride.user_id == user_id)
        )
        for code, granted in user_override_result.all():
            (effective.add if granted else effective.discard)(code)

        return sorted(effective)


class OtpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, code_hash: str, expires_at: datetime) -> OtpCode:
        otp = OtpCode(tenant_id=tenant_id, user_id=user_id, code_hash=code_hash, expires_at=expires_at)
        self._session.add(otp)
        await self._session.flush()
        return otp

    async def get_latest_active(self, *, user_id: uuid.UUID) -> OtpCode | None:
        result = await self._session.execute(
            select(OtpCode)
            .where(OtpCode.user_id == user_id, OtpCode.consumed_at.is_(None))
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_consumed(self, otp_id: uuid.UUID) -> None:
        await self._session.execute(
            update(OtpCode).where(OtpCode.id == otp_id).values(consumed_at=datetime.now(timezone.utc))
        )

    async def increment_attempts(self, otp_id: uuid.UUID) -> None:
        await self._session.execute(
            update(OtpCode).where(OtpCode.id == otp_id).values(attempt_count=OtpCode.attempt_count + 1)
        )


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        device_label: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        record = UserSession(
            tenant_id=tenant_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            device_label=device_label,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_active_by_hash(self, refresh_token_hash: str) -> UserSession | None:
        result = await self._session.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == refresh_token_hash,
                UserSession.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> UserSession | None:
        result = await self._session.execute(
            select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_id: uuid.UUID) -> None:
        await self._session.execute(
            update(UserSession).where(UserSession.id == session_id).values(revoked_at=datetime.now(timezone.utc))
        )

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[UserSession]:
        result = await self._session.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.issued_at.desc())
        )
        return list(result.scalars().all())
