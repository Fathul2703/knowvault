"""Composition root for the HTTP API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.config import Settings, get_settings
from knowvault.core.db import Database
from knowvault.core.errors import register_error_handlers
from knowvault.core.health import router as health_router
from knowvault.core.logging import configure_logging
from knowvault.core.middleware import (
    BodySizeLimitMiddleware,
    CsrfProtectionMiddleware,
    RequestContextMiddleware,
)
from knowvault.core.storage import ObjectStorage
from knowvault.modules.identity.router import router as identity_router
from knowvault.modules.ingestion.api.router import router as ingestion_router
from knowvault.modules.library.router import UPLOAD_PATH
from knowvault.modules.library.router import router as library_router

API_VERSION = "0.2.0"
# Room for multipart boundaries and form fields around the file itself.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}_{route.name}"


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    storage: ObjectStorage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    database = database or Database(settings)
    storage = storage or FilesystemStorage(settings.storage_dir)
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await database.dispose()

    app = FastAPI(
        title="KnowVault API",
        version=API_VERSION,
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.state.settings = settings
    app.state.database = database
    app.state.storage = storage

    register_error_handlers(app)
    # Middleware added last runs first: request context wraps everything so rejections are
    # logged, and CSRF checks run before any upload body is read.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_upload_bytes + _MULTIPART_OVERHEAD_BYTES,
        paths=[UPLOAD_PATH],
    )
    app.add_middleware(
        CsrfProtectionMiddleware, allowed_origin=settings.app_origin, non_json_paths=[UPLOAD_PATH]
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(library_router)
    app.include_router(ingestion_router)
    return app
