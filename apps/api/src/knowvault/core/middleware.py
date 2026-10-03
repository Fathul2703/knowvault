"""ASGI middleware: request context/logging, upload size limits and CSRF protection."""

import logging
import re
import time
import uuid
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from knowvault.core.errors import Problem, problem_response
from knowvault.core.logging import request_id_var

logger = logging.getLogger("knowvault.request")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# API responses are data (JSON, event streams, file downloads), never pages: nothing in them may
# run, load resources or be framed. The interactive docs (development only) are pages.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'; sandbox"
_DOCS_PREFIX = "/api/docs"


class RequestContextMiddleware:
    """Assigns a request ID, adds baseline headers and logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_PATTERN.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["x-request-id"] = request_id
                headers["x-content-type-options"] = "nosniff"
                headers.setdefault("cache-control", "no-store")
                headers.setdefault("referrer-policy", "no-referrer")
                headers.setdefault("cross-origin-resource-policy", "same-origin")
                if not scope["path"].startswith(_DOCS_PREFIX):
                    headers.setdefault("content-security-policy", API_CONTENT_SECURITY_POLICY)
                    headers.setdefault("x-frame-options", "DENY")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than `max_bytes` on the given paths with 413.

    The limit is enforced on the bytes actually received, not only on `Content-Length`, so
    chunked uploads cannot bypass it. Once the limit is crossed the application sees a client
    disconnect, and whatever response it produces is replaced by the 413 problem response.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, paths: Iterable[str]) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.paths = frozenset(paths)

    def _too_large(self) -> Response:
        return problem_response(
            Problem(
                title="Payload too large",
                status=413,
                code="payload_too_large",
                detail=f"The upload limit is {self.max_bytes // (1024 * 1024)} MB.",
            )
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in UNSAFE_METHODS
            or scope["path"] not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._too_large()(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await self._too_large()(scope, receive, send)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)


class CsrfProtectionMiddleware:
    """Rejects cross-site state-changing requests.

    Browsers attach `Origin` (or at least `Sec-Fetch-Site`) to state-changing requests, so a
    mismatch means the request was triggered by another site. Requests with neither header come
    from non-browser clients, which cannot ride on a victim's cookies. Requiring a JSON body
    additionally blocks HTML form posts, which cannot set that content type.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origin: str,
        protected_prefix: str = "/api/",
        non_json_paths: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.allowed_origin = allowed_origin
        self.protected_prefix = protected_prefix
        self.non_json_paths = frozenset(non_json_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in UNSAFE_METHODS
            or not scope["path"].startswith(self.protected_prefix)
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get("origin")
        fetch_site = headers.get("sec-fetch-site")
        if (origin is not None and origin.rstrip("/") != self.allowed_origin) or (
            origin is None and fetch_site not in (None, "same-origin", "none")
        ):
            response = problem_response(
                Problem(
                    title="Request origin not allowed",
                    status=403,
                    code="forbidden_origin",
                    detail="State-changing requests must come from the KnowVault web app.",
                )
            )
            await response(scope, receive, send)
            return

        has_body = headers.get("content-length", "0") != "0" or "transfer-encoding" in headers
        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if (
            has_body
            and scope["path"] not in self.non_json_paths
            and content_type != "application/json"
        ):
            response = problem_response(
                Problem(
                    title="Unsupported media type",
                    status=415,
                    code="unsupported_media_type",
                    detail="Request bodies must be sent as application/json.",
                )
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
