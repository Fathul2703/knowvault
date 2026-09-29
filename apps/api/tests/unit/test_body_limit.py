"""BodySizeLimitMiddleware, tested against a minimal ASGI app."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from knowvault.core.middleware import BodySizeLimitMiddleware


async def echo_length(scope: Scope, receive: Receive, send: Send) -> None:
    request = Request(scope, receive)
    try:
        body = await request.body()
        response = JSONResponse({"received": len(body)})
    except Exception:
        response = JSONResponse({"error": "client disconnected"}, status_code=400)
    await response(scope, receive, send)


def client() -> AsyncClient:
    app = BodySizeLimitMiddleware(echo_length, max_bytes=100, paths=["/upload"])
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def chunks(total: int, size: int = 30) -> AsyncIterator[bytes]:
    for start in range(0, total, size):
        yield b"x" * min(size, total - start)


async def test_allows_bodies_within_the_limit() -> None:
    async with client() as http:
        response = await http.post("/upload", content=b"x" * 100)
    assert response.json() == {"received": 100}


async def test_rejects_declared_oversized_body() -> None:
    async with client() as http:
        response = await http.post("/upload", content=b"x" * 101)
    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


async def test_rejects_oversized_chunked_body_without_content_length() -> None:
    async with client() as http:
        response = await http.post("/upload", content=chunks(250))
    assert response.status_code == 413


async def test_other_paths_are_not_limited() -> None:
    async with client() as http:
        response = await http.post("/elsewhere", content=b"x" * 500)
    assert response.json() == {"received": 500}
