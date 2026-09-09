import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _normalize_asyncpg_ssl_params(url: str) -> str:
    """Neon (and most managed Postgres providers) hand out a libpq-style
    connection string using `sslmode=require` — that works as-is for the
    sync psycopg2 URL (DATABASE_URL_SYNC), but asyncpg's `connect()` has no
    `sslmode` keyword at all (only `ssl`), and SQLAlchemy's asyncpg dialect
    passes every URL query param straight through as a connect() kwarg
    (`create_connect_args` in sqlalchemy/dialects/postgresql/asyncpg.py) —
    so a bare `postgresql+asyncpg://...?sslmode=require` URL raises
    `TypeError: connect() got an unexpected keyword argument 'sslmode'` on
    the very first connection, not at import time, which makes it an
    unpleasant surprise to debug against a live deployment. This rewrites
    `sslmode=` to `ssl=` (asyncpg accepts the same require/verify-full/...
    string values) and drops `channel_binding` (a libpq-only param asyncpg
    also doesn't accept) — only for `+asyncpg` URLs; DATABASE_URL_SYNC is
    left untouched since psycopg2 wants `sslmode` as-is."""
    if "+asyncpg" not in url:
        return url

    scheme, netloc, path, query, fragment = urlsplit(url)
    params = dict(parse_qsl(query, keep_blank_values=True))
    if "sslmode" in params:
        params["ssl"] = params.pop("sslmode")
    params.pop("channel_binding", None)
    return urlunsplit((scheme, netloc, path, urlencode(params), fragment))


class Settings(BaseSettings):
    """Central app configuration, loaded from environment variables (and a
    local .env file in dev). See .env.example for the full list."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic_erp"
    database_url_sync: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/clinic_erp"

    @field_validator("database_url")
    @classmethod
    def _fix_asyncpg_ssl(cls, v: str) -> str:
        return _normalize_asyncpg_ssl_params(v)

    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5

    staff_invite_expire_hours: int = 72

    # `NoDecode` opts this field out of pydantic-settings' default behavior
    # for list-typed env vars, which is to *require* JSON syntax and raise
    # a hard SettingsError before any field_validator even runs otherwise
    # (confirmed empirically — a `mode="before"` validator alone is too
    # late to intercept a plain comma string here). With NoDecode, the raw
    # env string reaches the validator below untouched, which then accepts
    # either a JSON array (`["https://a.com","https://b.com"]`, the
    # existing dev-.env format) or a plain comma-separated string
    # (`https://a.com,https://b.com`) — Koyeb's dashboard env-var editor is
    # a single text field, and typing a comma list there is far less
    # error-prone than hand-quoting a JSON array.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return v

    # File storage (§15) — "local" writes to disk under file_storage_local_dir,
    # for dev/self-hosted use; an "s3" backend can be added later behind the
    # same FileStorageBackend interface (app/core/storage.py) without any
    # caller change. No S3/R2 credentials exist in this environment yet, so
    # only "local" is actually implemented.
    file_storage_backend: str = "local"
    file_storage_local_dir: str = "./var/uploads"

    # Notification channel adapters (§16) — "console" (default) logs the
    # message and simulates success, no real send. Swap to a real provider
    # later purely via config; see app/modules/notifications/adapters.py.
    sms_provider: str = "console"
    whatsapp_provider: str = "console"
    email_provider: str = "console"

    # Payment gateway adapter (§17) — "mock" (default) simulates a gateway
    # order/intent with no real payment created. Swap to "razorpay"/
    # "cashfree" later purely via config; see
    # app/modules/billing/payment_gateway.py.
    payment_gateway_provider: str = "mock"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
