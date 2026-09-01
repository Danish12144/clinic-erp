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

    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
