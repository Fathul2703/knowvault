"""Cross-site request protection for state-changing API calls."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

LOGIN = "/api/v1/auth/login"
CREDENTIALS = {"email": "ada@example.com", "password": "whatever-it-is"}


def _bare_client(app: FastAPI) -> AsyncClient:
    """A client that sends no Origin header, like curl or another server."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_rejects_foreign_origin(app: FastAPI) -> None:
    async with _bare_client(app) as http:
        response = await http.post(
            LOGIN, json=CREDENTIALS, headers={"Origin": "https://evil.example"}
        )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden_origin"


async def test_rejects_cross_site_fetch_without_origin(app: FastAPI) -> None:
    async with _bare_client(app) as http:
        response = await http.post(
            LOGIN, json=CREDENTIALS, headers={"Sec-Fetch-Site": "cross-site"}
        )
    assert response.status_code == 403


async def test_allows_non_browser_clients(app: FastAPI) -> None:
    async with _bare_client(app) as http:
        response = await http.post(LOGIN, json=CREDENTIALS)
    # Reaches the endpoint (and fails authentication) instead of being blocked.
    assert response.status_code == 401


async def test_rejects_form_encoded_bodies(client: AsyncClient) -> None:
    response = await client.post(LOGIN, data=CREDENTIALS)
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media_type"


async def test_safe_methods_are_not_checked(app: FastAPI) -> None:
    async with _bare_client(app) as http:
        response = await http.get("/api/v1/auth/me", headers={"Origin": "https://evil.example"})
    assert response.status_code == 401
