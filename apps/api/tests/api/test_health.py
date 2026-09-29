from httpx import ASGITransport, AsyncClient

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.main import create_app


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


async def test_readiness_checks_database(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


async def test_readiness_reports_unreachable_database(settings: Settings) -> None:
    broken = settings.model_copy(
        update={"database_url": "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/missing_test"}
    )
    database = Database(broken, use_null_pool=True)
    app = create_app(broken, database)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        response = await http.get("/readyz")
    await database.dispose()
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "failed"}}


async def test_responses_carry_request_id_and_security_headers(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


async def test_invalid_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"
    assert len(response.headers["x-request-id"]) == 32
