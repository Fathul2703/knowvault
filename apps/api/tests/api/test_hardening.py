"""Limits on expensive endpoints, per-address login limits, headers and account deletion."""

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.core.middleware import API_CONTENT_SECURITY_POLICY
from knowvault.modules.assistant.infrastructure.models import Message
from knowvault.modules.identity.models import User
from knowvault.modules.library.models import Document
from knowvault.worker import build_pipeline, run_once
from tests.conftest import RegisterFn

PASSWORD = "correct horse battery"


@pytest.fixture
def run_worker(settings: Settings, database: Database) -> Callable[[], Awaitable[None]]:
    pipeline = build_pipeline(settings, database)

    async def _run() -> None:
        while await run_once(database, pipeline, settings):
            pass

    return _run


def limit(app: FastAPI, settings: Settings, **changes: object) -> None:
    app.state.settings = settings.model_copy(update=changes)


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register(email="ada@example.com", password=PASSWORD)
    return client


async def note(client: AsyncClient, title: str = "Note", body: str = "Some text.") -> int:
    response = await client.post("/api/v1/notes", json={"title": title, "body_md": body})
    return response.status_code


class TestHeaders:
    async def test_api_responses_cannot_run_or_be_framed(self, client: AsyncClient) -> None:
        for response in (await client.get("/healthz"), await client.get("/api/v1/auth/me")):
            assert response.headers["content-security-policy"] == API_CONTENT_SECURITY_POLICY
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            assert response.headers["cache-control"] == "no-store"

    async def test_interactive_docs_are_exempt(self, client: AsyncClient) -> None:
        response = await client.get("/api/docs")
        assert response.status_code == 200
        assert "content-security-policy" not in response.headers


class TestUserLimits:
    async def test_searches_per_minute(
        self, ada: AsyncClient, app: FastAPI, settings: Settings
    ) -> None:
        limit(app, settings, searches_per_minute=2)
        statuses = [
            (await ada.post("/api/v1/retrieval/search", json={"query": "x"})).status_code
            for _ in range(3)
        ]
        assert statuses == [200, 200, 429]

    async def test_document_writes_per_hour(
        self, ada: AsyncClient, app: FastAPI, settings: Settings
    ) -> None:
        limit(app, settings, document_writes_per_hour=1)
        assert await note(ada) == 201
        response = await ada.post("/api/v1/notes", json={"title": "Two", "body_md": "Text."})
        assert response.status_code == 429
        assert response.json()["code"] == "rate_limited"
        assert int(response.headers["Retry-After"]) > 0

    async def test_document_quota(self, ada: AsyncClient, app: FastAPI, settings: Settings) -> None:
        limit(app, settings, max_documents_per_user=1)
        assert await note(ada) == 201
        response = await ada.post("/api/v1/notes", json={"title": "Two", "body_md": "Text."})
        assert response.status_code == 409
        assert response.json()["code"] == "document_quota_exceeded"
        upload = await ada.post(
            "/api/v1/documents", files={"file": ("a.txt", b"hello", "text/plain")}
        )
        assert upload.json()["code"] == "document_quota_exceeded"

    async def test_questions_per_minute(
        self, ada: AsyncClient, app: FastAPI, settings: Settings
    ) -> None:
        limit(app, settings, chat_questions_per_minute=1)
        conversation = (await ada.post("/api/v1/conversations", json={})).json()["id"]
        ask = f"/api/v1/conversations/{conversation}/messages"
        assert (await ada.post(ask, json={"content": "First?"})).status_code == 200
        second = await ada.post(ask, json={"content": "Second?"})
        assert second.status_code == 429
        assert "questions" in second.json()["detail"]


class TestAddressLimits:
    async def test_failed_logins_per_address_across_emails(
        self,
        app: FastAPI,
        settings: Settings,
        app_client_factory: Callable[[], AsyncClient],
        register: RegisterFn,
    ) -> None:
        await register(email="ada@example.com", password=PASSWORD)
        limit(app, settings, login_ip_max_attempts=2)
        async with app_client_factory() as attacker:
            for email in ("a@example.com", "b@example.com"):
                response = await attacker.post(
                    "/api/v1/auth/login", json={"email": email, "password": "wrong password"}
                )
                assert response.status_code == 401
            blocked = await attacker.post(
                "/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
            )
            assert blocked.status_code == 429

    async def test_trusted_proxy_addresses_are_limited_separately(
        self, app: FastAPI, settings: Settings, app_client_factory: Callable[[], AsyncClient]
    ) -> None:
        # The test transport connects from 127.0.0.1, here the trusted proxy.
        limit(app, settings, login_ip_max_attempts=1, trusted_proxies="127.0.0.1")
        async with app_client_factory() as proxy:

            async def attempt(client_ip: str) -> int:
                response = await proxy.post(
                    "/api/v1/auth/login",
                    json={"email": "x@example.com", "password": "wrong password"},
                    headers={"X-Forwarded-For": client_ip},
                )
                return response.status_code

            assert await attempt("198.51.100.1") == 401
            assert await attempt("198.51.100.1") == 429
            assert await attempt("198.51.100.2") == 401

    async def test_registrations_per_address(
        self, client: AsyncClient, app: FastAPI, settings: Settings
    ) -> None:
        limit(app, settings, register_ip_max_attempts=2)
        body = {
            "invite_code": "not-a-real-invite-code",
            "email": "x@example.com",
            "password": PASSWORD,
            "display_name": "X",
        }
        statuses = [
            (await client.post("/api/v1/auth/register", json=body)).status_code for _ in range(3)
        ]
        assert statuses == [400, 400, 429]


class TestAccountDeletion:
    async def test_wrong_password_keeps_the_account(self, ada: AsyncClient) -> None:
        response = await ada.request(
            "DELETE", "/api/v1/auth/me", json={"password": "not my password"}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "invalid_password"
        assert (await ada.get("/api/v1/auth/me")).status_code == 200

    async def test_deletes_the_user_their_data_and_files(
        self,
        ada: AsyncClient,
        app_client_factory: Callable[[], AsyncClient],
        make_invite: Callable[[], Awaitable[str]],
        database: Database,
        settings: Settings,
        run_worker: Callable[[], Awaitable[None]],
    ) -> None:
        upload = await ada.post(
            "/api/v1/documents", files={"file": ("a.txt", b"hello world", "text/plain")}
        )
        assert upload.status_code == 202
        assert await note(ada, "Leave", "Employees get twelve days of annual leave.") == 201
        await run_worker()
        # An answer citing the user's own chunk: deleting the account must remove the citation
        # once, not also try to clear its chunk reference (both paths cascade from the user).
        conversation = (await ada.post("/api/v1/conversations", json={})).json()["id"]
        answer = await ada.post(
            f"/api/v1/conversations/{conversation}/messages",
            json={"content": "How many days of annual leave do employees get?"},
        )
        assert '"status":"complete"' in answer.text
        stored = [path for path in Path(settings.storage_dir).rglob("*") if path.is_file()]
        assert stored

        async with app_client_factory() as bob:
            await bob.post(
                "/api/v1/auth/register",
                json={
                    "invite_code": await make_invite(),
                    "email": "bob@example.com",
                    "password": PASSWORD,
                    "display_name": "Bob",
                },
            )
            assert await note(bob, "Bob's") == 201

            response = await ada.request("DELETE", "/api/v1/auth/me", json={"password": PASSWORD})
            assert response.status_code == 204
            assert "kv_session=" in response.headers["set-cookie"]

            assert (await ada.get("/api/v1/auth/me")).status_code == 401
            login = await ada.post(
                "/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD}
            )
            assert login.status_code == 401
            assert not any(path.exists() for path in stored)
            async with database.sessionmaker() as session:
                assert await session.scalar(select(func.count()).select_from(User)) == 1
                assert await session.scalar(select(func.count()).select_from(Document)) == 1
                assert await session.scalar(select(func.count()).select_from(Message)) == 0
            # Other users keep everything.
            assert len((await bob.get("/api/v1/documents")).json()["items"]) == 1
