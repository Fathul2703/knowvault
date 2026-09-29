"""Liveness and readiness probes."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from knowvault.core.db import Database, get_database

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, Literal["ok", "failed"]] = {}


@router.get("/healthz", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """The process is up. Does not touch dependencies."""
    return HealthStatus(status="ok")


@router.get(
    "/readyz",
    response_model=HealthStatus,
    responses={503: {"model": HealthStatus}},
)
async def readiness(
    database: Annotated[Database, Depends(get_database)],
) -> HealthStatus | JSONResponse:
    """The API can serve traffic: its dependencies are reachable."""
    try:
        await database.ping()
    except Exception:
        logger.warning("readiness_check_failed", extra={"dependency": "database"}, exc_info=True)
        body = HealthStatus(status="unavailable", checks={"database": "failed"})
        return JSONResponse(body.model_dump(), status_code=503)
    return HealthStatus(status="ok", checks={"database": "ok"})
