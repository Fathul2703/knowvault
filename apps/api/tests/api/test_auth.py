from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.modules.identity.models import Invite, UserSession
from knowvault.modules.identity.service import IdentityService
from tests.conftest import RegisterFn

PASSWORD = "correct horse battery"
MakeInvite = Callable[[], Awaitable[str]]


def _registration(invite_code: str, email: str = "ada@example.com") -> dict[str, str]:
    return {
        "invite_code": invite_code,
        "email": email,
        "password": PASSWORD,
        "display_name": "Ada",
    }


class TestRegister:
    async def test_creates_user_and_signs_in(
        self, client: AsyncClient, make_invite: MakeInvite, settings: Settings
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register", json=_registration(await make_invite(), "Ada@Example.COM")
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "ada@example.com"
        assert body["display_name"] == "Ada"
        assert "password_hash" not in body

        cookie = response.headers["set-cookie"]
        assert cookie.startswith(f"{settings.session_cookie_name}=")
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["id"] == body["id"]

    async def test_rejects_unknown_invite(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/register", json=_registration("nope"))
        assert response.status_code == 400
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "invalid_invite"

    async def test_invite_is_single_use(self, client: AsyncClient, make_invite: MakeInvite) -> None:
        code = await make_invite()
        first = await client.post("/api/v1/auth/register", json=_registration(code))
        second = await client.post(
            "/api/v1/auth/register", json=_registration(code, "grace@example.com")
        )
        assert first.status_code == 201
        assert second.status_code == 400
        assert second.json()["code"] == "invalid_invite"

    async def test_rejects_expired_invite(
        self, client: AsyncClient, make_invite: MakeInvite, database: Database
    ) -> None:
        code = await make_invite()
        async with database.sessionmaker() as session:
            await session.execute(
                update(Invite).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
            await session.commit()
        response = await client.post("/api/v1/auth/register", json=_registration(code))
        assert response.status_code == 400

    async def test_rejects_duplicate_email_and_keeps_invite_usable(
        self, client: AsyncClient, make_invite: MakeInvite, register: RegisterFn
    ) -> None:
        await register(email="ada@example.com")
        code = await make_invite()
        duplicate = await client.post(
            "/api/v1/auth/register", json=_registration(code, "ADA@example.com")
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "email_taken"
        # The failed attempt must not burn the invite.
        retry = await client.post(
            "/api/v1/auth/register", json=_registration(code, "grace@example.com")
        )
        assert retry.status_code == 201

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("password", "short"),
            ("password", "x" * 129),
            ("email", "not-an-email"),
            ("display_name", "   "),
        ],
    )
    async def test_validates_input(
        self, client: AsyncClient, make_invite: MakeInvite, field: str, value: str
    ) -> None:
        payload = _registration(await make_invite()) | {field: value}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "validation_error"
        assert any(field in error["loc"] for error in body["errors"])


class TestLogin:
    async def test_succeeds_with_correct_credentials(
        self, app_client_factory: Callable[[], AsyncClient], register: RegisterFn
    ) -> None:
        await register()
        async with app_client_factory() as fresh:
            response = await fresh.post(
                "/api/v1/auth/login", json={"email": "ADA@example.com", "password": PASSWORD}
            )
            assert response.status_code == 200
            assert (await fresh.get("/api/v1/auth/me")).status_code == 200

    @pytest.mark.parametrize(
        ("email", "password"),
        [("ada@example.com", "wrong password!"), ("nobody@example.com", PASSWORD)],
    )
    async def test_failure_does_not_reveal_which_part_was_wrong(
        self,
        app_client_factory: Callable[[], AsyncClient],
        register: RegisterFn,
        email: str,
        password: str,
    ) -> None:
        await register()
        async with app_client_factory() as fresh:
            response = await fresh.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"
        assert "set-cookie" not in response.headers

    async def test_locks_out_after_repeated_failures(
        self, client: AsyncClient, register: RegisterFn, settings: Settings
    ) -> None:
        await register()
        for _ in range(settings.login_max_attempts):
            failed = await client.post(
                "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong!"}
            )
            assert failed.status_code == 401

        # Even the correct password is refused until the window resets.
        locked = await client.post(
            "/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
        )
        assert locked.status_code == 429
        assert locked.json()["code"] == "rate_limited"
        assert int(locked.headers["retry-after"]) > 0


class TestSession:
    async def test_me_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["code"] == "not_authenticated"

    async def test_logout_revokes_the_session(
        self, client: AsyncClient, register: RegisterFn, settings: Settings
    ) -> None:
        await register()
        token = client.cookies[settings.session_cookie_name]

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401

        # Replaying the old cookie must not work either.
        client.cookies.set(settings.session_cookie_name, token)
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_idle_session_expires(
        self, client: AsyncClient, register: RegisterFn, database: Database, settings: Settings
    ) -> None:
        await register()
        idle = timedelta(hours=settings.session_idle_ttl_hours, seconds=1)
        async with database.sessionmaker() as session:
            await session.execute(update(UserSession).values(last_seen_at=datetime.now(UTC) - idle))
            await session.commit()
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_absolute_expiry(
        self, client: AsyncClient, register: RegisterFn, database: Database
    ) -> None:
        await register()
        async with database.sessionmaker() as session:
            await session.execute(update(UserSession).values(expires_at=datetime.now(UTC)))
            await session.commit()
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_password_reset_revokes_sessions(
        self, client: AsyncClient, register: RegisterFn, service: IdentityService
    ) -> None:
        await register()
        await service.reset_password(email="ada@example.com", new_password="another long secret")
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        relogin = await client.post(
            "/api/v1/auth/login",
            json={"email": "ada@example.com", "password": "another long secret"},
        )
        assert relogin.status_code == 200

    async def test_each_session_resolves_to_its_own_user(
        self,
        client: AsyncClient,
        app_client_factory: Callable[[], AsyncClient],
        make_invite: MakeInvite,
        register: RegisterFn,
    ) -> None:
        ada = await register(email="ada@example.com")
        async with app_client_factory() as other:
            assert (await other.get("/api/v1/auth/me")).status_code == 401
            grace = await other.post(
                "/api/v1/auth/register",
                json=_registration(await make_invite(), "grace@example.com"),
            )
            assert (await other.get("/api/v1/auth/me")).json()["id"] == grace.json()["id"]
        assert (await client.get("/api/v1/auth/me")).json()["id"] == ada["id"]
