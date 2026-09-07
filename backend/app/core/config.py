from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app configuration, loaded from environment variables (and a
    local .env file in dev). See .env.example for the full list."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/clinic_erp"
    database_url_sync: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/clinic_erp"

    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    otp_expire_minutes: int = 5
    otp_max_attempts: int = 5

    staff_invite_expire_hours: int = 72

    cors_origins: list[str] = ["http://localhost:3000"]

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
