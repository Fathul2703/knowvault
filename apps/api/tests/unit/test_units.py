"""Pure unit tests: no database or HTTP."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from knowvault.core.config import Environment, Settings
from knowvault.core.rate_limit import seconds_until_reset, window_start_for
from knowvault.modules.identity.credentials import (
    hash_password,
    hash_token,
    new_token,
    verify_password,
)

DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


class TestCredentials:
    def test_password_round_trip(self) -> None:
        hashed = hash_password("correct horse battery")
        assert hashed.startswith("$argon2id$")
        assert verify_password(hashed, "correct horse battery")

    def test_wrong_password_is_rejected(self) -> None:
        assert not verify_password(hash_password("correct horse battery"), "wrong password!")

    def test_missing_hash_is_rejected(self) -> None:
        assert not verify_password(None, "anything at all")

    def test_malformed_hash_is_rejected(self) -> None:
        assert not verify_password("not-a-hash", "anything at all")

    def test_tokens_are_unique_and_hash_deterministically(self) -> None:
        first, second = new_token(), new_token()
        assert first != second
        assert len(first) >= 43  # 32 random bytes, base64url encoded
        assert hash_token(first) == hash_token(first)
        assert hash_token(first) != hash_token(second)


class TestSettings:
    def test_rejects_non_asyncpg_url(self) -> None:
        with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
            Settings(database_url="postgresql://u:p@localhost/db")

    def test_production_requires_secure_cookies(self) -> None:
        with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE"):
            Settings(
                database_url=DB_URL,
                environment=Environment.PRODUCTION,
                app_origin="https://knowvault.example",
            )

    def test_production_requires_https_origin(self) -> None:
        with pytest.raises(ValidationError, match="https"):
            Settings(
                database_url=DB_URL,
                environment=Environment.PRODUCTION,
                session_cookie_secure=True,
                app_origin="http://knowvault.example",
            )

    def test_cookie_name_uses_host_prefix_only_when_secure(self) -> None:
        insecure = Settings(database_url=DB_URL)
        secure = Settings(database_url=DB_URL, session_cookie_secure=True)
        assert insecure.session_cookie_name == "kv_session"
        assert secure.session_cookie_name == "__Host-kv_session"

    def test_origin_trailing_slash_is_normalised(self) -> None:
        settings = Settings(database_url=DB_URL, app_origin="http://localhost:3000/")
        assert settings.app_origin == "http://localhost:3000"


class TestRateLimitWindows:
    def test_window_start_is_aligned(self) -> None:
        now = datetime(2026, 1, 1, 10, 7, 30, tzinfo=UTC)
        assert window_start_for(now, timedelta(minutes=15)) == datetime(
            2026, 1, 1, 10, 0, tzinfo=UTC
        )

    def test_seconds_until_reset(self) -> None:
        now = datetime(2026, 1, 1, 10, 14, 0, tzinfo=UTC)
        assert seconds_until_reset(now, timedelta(minutes=15)) == 60
