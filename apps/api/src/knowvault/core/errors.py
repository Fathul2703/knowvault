"""Application errors rendered as RFC 9457 Problem Details."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class Problem(BaseModel):
    """Error body returned by every failing endpoint."""

    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: list[dict[str, Any]] | None = None


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code = 400
    code = "bad_request"
    title = "Bad request"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"
    title = "Authentication required"


class ForbiddenOriginError(AppError):
    status_code = 403
    code = "forbidden_origin"
    title = "Request origin not allowed"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    title = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    title = "Conflict"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    title = "Too many requests"

    def __init__(self, detail: str | None = None, *, retry_after_seconds: int) -> None:
        super().__init__(detail)
        self.retry_after_seconds = retry_after_seconds


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    headers = None
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    problem = Problem(title=exc.title, status=exc.status_code, code=exc.code, detail=exc.detail)
    return problem_response(problem, headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    problem = Problem(
        title="Validation failed",
        status=422,
        code="validation_error",
        detail="The request body or parameters are invalid.",
        errors=errors,
    )
    return problem_response(problem)


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    problem = Problem(title=str(exc.detail), status=exc.status_code, code=f"http_{exc.status_code}")
    return problem_response(problem, dict(exc.headers) if exc.headers else None)


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", exc_info=exc)
    problem = Problem(title="Internal server error", status=500, code="internal_error")
    return problem_response(problem)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
