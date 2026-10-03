"""Application settings, loaded from environment variables."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, PostgresDsn, SecretStr, model_validator
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

    # --- Embeddings -------------------------------------------------------------------------
    # "bge-m3": BAAI/bge-m3 (int8 ONNX) run locally; "fake": deterministic, for tests only.
    embedding_provider: Literal["bge-m3", "fake"] = "bge-m3"
    # Where model files are downloaded; shared by the API and the worker.
    embedding_cache_dir: Path = Path("data/models")
    # ONNX Runtime threads per process; None lets the runtime decide.
    embedding_threads: int | None = Field(default=None, ge=1)
    embedding_batch_size: int = Field(default=8, ge=1)

    # --- Chat (grounded answers) -------------------------------------------------------------
    # "anthropic": Claude through the Anthropic API (needs ANTHROPIC_API_KEY); "fake": an
    # offline, extractive stand-in so the stack runs without a key (development and tests).
    llm_provider: Literal["anthropic", "fake"] = "fake"
    # Writes answers.
    llm_model: str = "claude-sonnet-5-5"
    # Cheaper model that rewrites follow-up questions into standalone search queries.
    llm_fast_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=60, gt=0)
    chat_max_output_tokens: int = Field(default=1024, ge=64)
    # Sources given to the model per answer, and the characters they may take in total.
    chat_max_sources: int = Field(default=8, ge=1, le=20)
    chat_context_chars: int = Field(default=24_000, ge=1000)
    # Earlier questions and answers sent with a new question.
    chat_history_turns: int = Field(default=4, ge=0)
    chat_history_chars: int = Field(default=6000, ge=0)
    # Tokens (input + output) one user may spend per UTC day.
    chat_daily_token_limit: int = Field(default=200_000, ge=1)

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
            if self.embedding_provider == "fake":
                raise ValueError("EMBEDDING_PROVIDER=fake is for tests only")
            if self.llm_provider == "fake":
                raise ValueError("LLM_PROVIDER=fake is for development and tests only")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
