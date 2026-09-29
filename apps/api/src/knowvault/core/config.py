"""Application settings, loaded from environment variables."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
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

    # --- Library & ingestion ---------------------------------------------------------------
    # Directory for uploaded files, shared by the API and the worker.
    storage_dir: Path = Path("data/uploads")
    max_upload_mb: int = Field(default=25, ge=1)
    max_note_chars: int = Field(default=200_000, ge=1)
    max_pages: int = Field(default=500, ge=1)
    max_extracted_chars: int = Field(default=5_000_000, ge=1)
    parse_timeout_seconds: float = Field(default=60, gt=0)
    parse_memory_mb: int = Field(default=1024, ge=64)

    worker_poll_interval_seconds: float = Field(default=1.0, gt=0)
    job_max_attempts: int = Field(default=3, ge=1)
    # A running job whose worker has been silent this long is considered abandoned.
    job_lock_timeout_seconds: int = Field(default=600, ge=30)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

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
