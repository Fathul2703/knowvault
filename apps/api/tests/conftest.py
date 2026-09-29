"""Shared fixtures. Tests run against a real PostgreSQL database.

Set TEST_DATABASE_URL to a database whose name ends in `_test`; it is dropped and recreated
at the start of every test session.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.config import Environment, Settings
from knowvault.core.db import Database
from knowvault.main import create_app
from knowvault.modules.identity.service import IdentityService

API_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://knowvault:knowvault@localhost:5432/knowvault_test"
TEST_ORIGIN = "http://testserver"
TABLES = (
    "jobs",
    "chunks",
    "notes",
    "documents",
    "collections",
    "usage_counters",
    "sessions",
    "invites",
    "users",
)


async def _recreate_database(url: str) -> None:
    parsed = make_url(url)
    name = parsed.database
    if not name or not name.endswith("_test"):
        raise RuntimeError(f"Refusing to recreate {name!r}: test database names must end in _test")
    admin_dsn = parsed.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    conn = await asyncpg.connect(admin_dsn)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    asyncio.run(_recreate_database(url))
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return url


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url=database_url,
        app_origin=TEST_ORIGIN,
        log_level="WARNING",
        storage_dir=tmp_path / "uploads",
        max_upload_mb=1,
        parse_timeout_seconds=30,
    )


@pytest.fixture
def storage(settings: Settings) -> FilesystemStorage:
    return FilesystemStorage(settings.storage_dir)


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    db = Database(settings, use_null_pool=True)
    yield db
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    await db.dispose()


@pytest.fixture
def app(settings: Settings, database: Database, storage: FilesystemStorage) -> FastAPI:
    return create_app(settings, database, storage)


@pytest.fixture
def app_client_factory(app: FastAPI) -> Callable[[], AsyncClient]:
    """Creates independent clients (separate cookie jars) that behave like the web app."""

    def _factory() -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=app),
            base_url=TEST_ORIGIN,
            headers={"Origin": TEST_ORIGIN},
        )

    return _factory


@pytest.fixture
async def client(app_client_factory: Callable[[], AsyncClient]) -> AsyncIterator[AsyncClient]:
    async with app_client_factory() as http:
        yield http


@pytest.fixture
async def service(settings: Settings, database: Database) -> AsyncIterator[IdentityService]:
    async with database.sessionmaker() as session:
        yield IdentityService(session, settings)


@pytest.fixture
def make_invite(service: IdentityService) -> Callable[[], Awaitable[str]]:
    return service.create_invite


RegisterFn = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
def register(client: AsyncClient, make_invite: Callable[[], Awaitable[str]]) -> RegisterFn:
    async def _register(
        email: str = "ada@example.com",
        password: str = "correct horse battery",
        display_name: str = "Ada",
    ) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "invite_code": await make_invite(),
                "email": email,
                "password": password,
                "display_name": display_name,
            },
        )
        assert response.status_code == 201, response.text
        body: dict[str, str] = response.json()
        return body

    return _register
