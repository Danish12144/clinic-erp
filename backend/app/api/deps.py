"""Shared FastAPI request dependencies. Every module's router depends on
these for authentication, tenant-scoped DB access, and permission checks —
see PRD-ARCHITECTURE.md §10 (backend architecture), §13 (RBAC strategy).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.db import tenant_session

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """The identity/authorization context extracted from a valid access
    token. `permissions` is the set resolved at the token's issuance time
    (login or refresh) — see app/core/security.py's module docstring."""

    user_id: UUID
    tenant_id: UUID
    role_code: str
    permissions: frozenset[str]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = security.decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Access token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from None

    return CurrentUser(
        user_id=UUID(payload["sub"]),
        tenant_id=UUID(payload["tenant_id"]),
        role_code=payload["role"],
        permissions=frozenset(payload.get("permissions", [])),
    )


async def get_tenant_db(current_user: CurrentUser = Depends(get_current_user)) -> AsyncIterator[AsyncSession]:
    """Tenant-scoped DB session for any authenticated route. Do not use
    this for pre-authentication flows (login, OTP request/verify) — those
    resolve their own tenant from a clinic slug; see
    app/modules/auth/service.py."""
    async with tenant_session(current_user.tenant_id) as session:
        yield session


def require_permission(permission_code: str):
    """Route-dependency factory: `Depends(require_permission("vitals.record"))`.

    Checks membership in the permission set already embedded in the access
    token (PRD §13) rather than hitting the DB on every request. A clinic
    owner revoking a permission takes effect for that user on their next
    token refresh.
    """

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if permission_code not in current_user.permissions:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing required permission: {permission_code}",
            )
        return current_user

    return _check


def require_any_permission(*permission_codes: str):
    """Like `require_permission`, but for a route two differently-scoped
    roles both reach through different permission codes — e.g. Billing's
    reads, where Owner/Receptionist hold `billing.manage` (full) and
    Doctor/Patient hold `billing.view_own` (row-scoped, enforced by the
    service layer, not here). First needed by the Billing module; earlier
    modules' "view" permission was always a single code shared by every
    role that could read at all.
    """

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(code in current_user.permissions for code in permission_codes):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Missing required permission: one of {', '.join(permission_codes)}",
            )
        return current_user

    return _check


def require_feature_flag(setting_key: str, *, default: bool = False):
    """Route-dependency factory gating a whole module behind a per-tenant
    on/off switch: `Depends(require_feature_flag("features.lab_enabled"))`.
    First needed by the Lab module (task: "lab routes... accessible only
    when lab feature flag is enabled for that clinic") but deliberately
    generic — any future optional/paid module can reuse it with its own
    `setting_key`.

    Reads the flag from the Tenancy module's generic `TenantSetting` bag
    (no new table) — an Owner toggles it via the existing
    `PUT /api/v1/clinics/me/settings/{key}` endpoint, nothing new to build
    for the toggle itself. Unlike `require_permission`, this always hits
    the DB (the flag isn't embedded in the JWT — it can change without a
    token refresh, and gating an entire module is rare enough not to
    warrant optimizing away the query).
    """

    async def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        # Local import: app.modules.tenancy would otherwise need to import
        # app.api.deps too (every module's router does), which would be a
        # circular import at module load time if this were a top-level import.
        from app.modules.tenancy.repository import TenantSettingRepository

        async with tenant_session(current_user.tenant_id) as session:
            setting = await TenantSettingRepository(session).get_by_key(tenant_id=current_user.tenant_id, key=setting_key)
        enabled = bool(setting.value) if setting is not None else default
        if not enabled:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This feature ('{setting_key}') is not enabled for this clinic",
            )
        return current_user

    return _check
