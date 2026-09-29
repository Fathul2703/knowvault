"""The document processing use case: extract → normalise → chunk → embed → store."""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knowvault.core import jobs
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.storage import ObjectStorage, StoredObjectNotFoundError
from knowvault.modules.ingestion.application.ports import ChunkWriter, DocumentParser
from knowvault.modules.ingestion.domain.chunking import (
    ChunkingConfig,
    chunk_blocks,
    embedding_text,
)
from knowvault.modules.ingestion.domain.model import (
    ChunkDraft,
    ExtractionError,
    FailureCode,
    failure_message,
)
from knowvault.modules.ingestion.domain.normalize import normalize_blocks
from knowvault.modules.library import processing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Result:
    chunks: list[ChunkDraft]
    embeddings: list[list[float]]
    page_count: int | None


class IngestionPipeline:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        parser: DocumentParser,
        chunk_writer: ChunkWriter,
        embeddings: EmbeddingModel,
        chunking: ChunkingConfig | None = None,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._parser = parser
        self._chunk_writer = chunk_writer
        self._embeddings = embeddings
        self._chunking = chunking or ChunkingConfig()

    async def process(self, job: jobs.ClaimedJob) -> None:
        """Processes one `process_document` job and records the outcome on job and document.

        * Document problems (corrupt, encrypted, no text, ...) fail permanently.
        * Anything else is retried with backoff; after the last attempt the document fails.
        * Results for an outdated `content_version` are discarded.
        """
        document_id = job.resource_id
        version = int(job.payload["content_version"])
        log = {"document_id": str(document_id), "job_id": str(job.id), "attempt": job.attempts}

        try:
            async with self._sessions() as session:
                target = await processing.start_processing(session, document_id, version)
            if target is None:
                logger.info("processing_skipped_stale", extra=log)
                await self._finish_job(job)
                return

            result = await self._extract_and_chunk(target)

            async with self._sessions() as session:
                if not await processing.lock_current_version(session, document_id, version):
                    logger.info("processing_discarded_stale", extra=log)
                    await jobs.mark_succeeded(session, job.id)
                    await session.commit()
                    return
                await self._chunk_writer.replace_chunks(
                    session,
                    document_id=document_id,
                    owner_id=target.owner_id,
                    chunks=result.chunks,
                    embeddings=result.embeddings,
                )
                await processing.mark_ready(
                    session,
                    document_id,
                    page_count=result.page_count,
                    embedding_model=self._embeddings.model_id,
                )
                await jobs.mark_succeeded(session, job.id)
                await session.commit()
            logger.info("document_processed", extra={**log, "chunks": len(result.chunks)})

        except ExtractionError as exc:
            logger.info("document_rejected", extra={**log, "code": exc.code.value})
            async with self._sessions() as session:
                await processing.mark_failed(
                    session, document_id, version, code=exc.code.value, detail=exc.message
                )
                await jobs.mark_failed(session, job.id, exc.code.value)
                await session.commit()

        except Exception as exc:
            logger.exception("document_processing_error", extra=log)
            async with self._sessions() as session:
                if await jobs.schedule_retry(session, job, repr(exc)):
                    await processing.mark_pending(session, document_id, version)
                else:
                    code = FailureCode.PROCESSING_ERROR
                    await processing.mark_failed(
                        session,
                        document_id,
                        version,
                        code=code.value,
                        detail=failure_message(code),
                    )
                await session.commit()

    async def _finish_job(self, job: jobs.ClaimedJob) -> None:
        async with self._sessions() as session:
            await jobs.mark_succeeded(session, job.id)
            await session.commit()

    async def _extract_and_chunk(self, target: processing.ProcessingInput) -> _Result:
        if target.note_body is not None:
            data = target.note_body.encode()
        elif target.storage_key is not None:
            try:
                data = await self._storage.read_bytes(target.storage_key)
            except StoredObjectNotFoundError as exc:
                raise ExtractionError(FailureCode.FILE_MISSING) from exc
        else:
            raise ExtractionError(FailureCode.FILE_MISSING)

        extraction = await self._parser.parse(data, target.mime_type)
        blocks = normalize_blocks(extraction.blocks)
        if not blocks:
            raise ExtractionError(FailureCode.NO_EXTRACTABLE_TEXT)
        chunks = chunk_blocks(blocks, self._chunking)
        # Computed before the storing transaction opens: embedding can take a while and must
        # not hold a database connection. Failures here are transient and retried.
        vectors = await self._embeddings.embed_documents(
            [embedding_text(target.title, chunk) for chunk in chunks]
        )
        return _Result(chunks, vectors, extraction.page_count)
