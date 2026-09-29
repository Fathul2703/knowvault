"""Application settings, loaded from environment variables."""

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    # Configuration comes only from the process environment. `make` and Docker Compose load
    # the repository's .env file; see .env.example.
    model_config = SettingsConfigDict(extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Must use the asyncpg driver, e.g. postgresql+asyncpg://user:pass@host:5432/db
    database_url: PostgresDsn
    database_pool_size: int = Field(default=5, ge=1)

    # Browser origin that serves the web app. State-changing requests must come from it.
    app_origin: str = "http://localhost:3000"

    session_cookie_secure: bool = False
    session_idle_ttl_hours: int = Field(default=24 * 7, ge=1)
    session_absolute_ttl_days: int = Field(default=30, ge=1)

    login_max_attempts: int = Field(default=5, ge=1)
    login_window_minutes: int = Field(default=15, ge=1)

    invite_ttl_days: int = Field(default=7, ge=1)

    @property
    def session_cookie_name(self) -> str:
        # The __Host- prefix is only honoured by browsers on secure cookies.
        return "__Host-kv_session" if self.session_cookie_secure else "kv_session"

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.database_url.scheme != "postgresql+asyncpg":
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        self.app_origin = self.app_origin.rstrip("/")
        if self.is_production:
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            if not self.app_origin.startswith("https://"):
                raise ValueError("APP_ORIGIN must use https in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
