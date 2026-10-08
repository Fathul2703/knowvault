"""Composition root for the background worker: `knowvault worker`."""

import asyncio
import contextlib
import logging
import signal
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.adapters.embeddings import build_embedding_model
from knowvault.adapters.storage.filesystem import FilesystemStorage
from knowvault.core import jobs
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.logging import configure_logging
from knowvault.core.storage import ObjectStorage
from knowvault.modules.graph.application.extraction import EXTRACT_GRAPH_JOB, GraphExtraction
from knowvault.modules.graph.domain.heuristic import HeuristicExtractor
from knowvault.modules.graph.infrastructure.store import PostgresGraphStore, queue_extraction
from knowvault.modules.ingestion.application.pipeline import IngestionPipeline
from knowvault.modules.ingestion.application.ports import DocumentReadyHook
from knowvault.modules.ingestion.domain.chunking import ChunkingConfig
from knowvault.modules.ingestion.infrastructure.chunks import SqlChunkWriter
from knowvault.modules.ingestion.infrastructure.subprocess_parser import (
    SubprocessDocumentParser,
)
from knowvault.modules.library.processing import PROCESS_DOCUMENT_JOB

logger = logging.getLogger("knowvault.worker")


def build_graph_extraction(
    settings: Settings, database: Database, embeddings: EmbeddingModel | None = None
) -> GraphExtraction | None:
    if settings.graph_extractor == "none":
        return None
    merge = settings.graph_merge_threshold < 1.0
    return GraphExtraction(
        database.sessionmaker,
        PostgresGraphStore(),
        HeuristicExtractor(settings.graph_max_entities_per_chunk),
        embeddings=(embeddings or build_embedding_model(settings)) if merge else None,
        merge_threshold=settings.graph_merge_threshold if merge else None,
    )


def build_pipeline(
    settings: Settings,
    database: Database,
    embeddings: EmbeddingModel | None = None,
    storage: ObjectStorage | None = None,
) -> IngestionPipeline:
    return IngestionPipeline(
        sessions=database.sessionmaker,
        storage=storage or FilesystemStorage(settings.storage_dir),
        parser=SubprocessDocumentParser(
            max_pages=settings.max_pages,
            max_chars=settings.max_extracted_chars,
            timeout_seconds=settings.parse_timeout_seconds,
            memory_mb=settings.parse_memory_mb,
        ),
        chunk_writer=SqlChunkWriter(),
        embeddings=embeddings or build_embedding_model(settings),
        chunking=ChunkingConfig(
            target_chars=settings.chunk_target_chars,
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
        ),
        on_ready=_graph_hook(settings) if settings.graph_extractor != "none" else None,
    )


def _graph_hook(settings: Settings) -> DocumentReadyHook:
    """Queues graph extraction when a document becomes ready."""

    async def on_ready(
        session: AsyncSession, *, document_id: uuid.UUID, content_version: int
    ) -> None:
        await queue_extraction(
            session,
            document_id=document_id,
            content_version=content_version,
            max_attempts=settings.job_max_attempts,
        )

    return on_ready


async def run_once(
    database: Database,
    pipeline: IngestionPipeline,
    settings: Settings,
    graph: GraphExtraction | None = None,
) -> bool:
    """Claims and runs one job. Returns False when the queue is empty."""
    async with database.sessionmaker() as session:
        job = await jobs.claim(
            session, lock_timeout=timedelta(seconds=settings.job_lock_timeout_seconds)
        )
    if job is None:
        return False
    if job.type == PROCESS_DOCUMENT_JOB:
        await pipeline.process(job)
    elif job.type == EXTRACT_GRAPH_JOB:
        graph = graph or build_graph_extraction(settings, database)
        if graph is not None:
            await graph.process(job)
        else:
            # Queued before GRAPH_EXTRACTOR was set to "none": nothing to do.
            async with database.sessionmaker() as session:
                await jobs.mark_succeeded(session, job.id)
                await session.commit()
    else:
        logger.error("unknown_job_type", extra={"job_id": str(job.id), "type": job.type})
        async with database.sessionmaker() as session:
            await jobs.mark_failed(session, job.id, f"unknown job type {job.type!r}")
            await session.commit()
    return True


async def run(settings: Settings) -> None:
    configure_logging(settings.log_level)
    database = Database(settings)
    # One embedding model for processing and the graph: it is loaded into memory once.
    embeddings = build_embedding_model(settings)
    pipeline = build_pipeline(settings, database, embeddings)
    graph = build_graph_extraction(settings, database, embeddings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    logger.info("worker_started")
    try:
        while not stop.is_set():
            try:
                worked = await run_once(database, pipeline, settings, graph)
            except Exception:
                # e.g. the database is briefly unavailable; keep the worker alive.
                logger.exception("worker_loop_error")
                worked = False
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), settings.worker_poll_interval_seconds)
    finally:
        await database.dispose()
        logger.info("worker_stopped")
