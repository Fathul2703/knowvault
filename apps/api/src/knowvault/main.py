"""Composition root for the HTTP API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from knowvault.adapters.chat import build_chat_models
from knowvault.adapters.embeddings import build_embedding_model
from knowvault.adapters.reranking import build_reranker
from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core.chat import ChatModels
from knowvault.core.config import Settings, get_settings
from knowvault.core.db import Database
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.errors import register_error_handlers
from knowvault.core.health import router as health_router
from knowvault.core.logging import configure_logging
from knowvault.core.middleware import (
    BodySizeLimitMiddleware,
    CsrfProtectionMiddleware,
    RequestContextMiddleware,
)
from knowvault.core.reranker import Reranker
from knowvault.core.storage import ObjectStorage
from knowvault.modules.assistant.api.router import router as assistant_router
from knowvault.modules.graph.api.router import router as graph_router
from knowvault.modules.graph.infrastructure.entity_links import build_entity_links
from knowvault.modules.identity.router import router as identity_router
from knowvault.modules.ingestion.api.router import router as ingestion_router
from knowvault.modules.library.router import UPLOAD_PATH
from knowvault.modules.library.router import router as library_router
from knowvault.modules.retrieval.api.router import router as retrieval_router

API_VERSION = "0.5.0"
# Room for multipart boundaries and form fields around the file itself.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}_{route.name}"


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    storage: ObjectStorage | None = None,
    embeddings: EmbeddingModel | None = None,
    chat_models: ChatModels | None = None,
    reranker: Reranker | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    database = database or Database(settings)
    storage = storage or FilesystemStorage(settings.storage_dir)
    # Loaded lazily on the first search, so startup and health checks stay fast.
    embeddings = embeddings or build_embedding_model(settings)
    chat_models = chat_models or build_chat_models(settings)
    reranker = reranker or build_reranker(settings)
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
    app.state.embeddings = embeddings
    app.state.chat_models = chat_models
    app.state.reranker = reranker
    app.state.entity_links = build_entity_links(settings.graph_retrieval)

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
    app.include_router(retrieval_router)
    app.include_router(assistant_router)
    app.include_router(graph_router)
    return app
