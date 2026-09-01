"""Password hashing, JWT access tokens, and the primitives behind opaque
refresh tokens and OTP codes. See PRD-ARCHITECTURE.md §12.

Design notes:
- Access tokens are JWTs and carry the user's *resolved* effective
  permission set (role defaults + permission_overrides, computed once at
  login/refresh — PRD §13) so permission checks on protected routes never
  need a DB round-trip. A permission revoked mid-session takes effect on
  the user's next token refresh, not instantly — an accepted tradeoff.
- Refresh tokens are NOT JWTs. They're random opaque strings, stored
  server-side only as a hash (never the raw value), which is what makes
  revocation ("log out this device") possible — a stateless JWT can't be
  revoked before it expires.
- OTP codes are likewise stored only as a hash.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

ACCESS_TOKEN_TYPE = "access"


def hash_password(raw_password: str) -> str:
    return _pwd_context.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(raw_password, password_hash)


def create_access_token(*, user_id: UUID, tenant_id: UUID, role_code: str, permissions: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role_code,
        "permissions": permissions,
        "token_type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.ExpiredSignatureError / jwt.InvalidTokenError on failure
    — callers (app/api/deps.py) translate these into HTTP 401s."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("token_type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("token is not an access token")
    return payload


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
