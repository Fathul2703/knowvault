"""Interfaces the ingestion use cases depend on; implemented in `infrastructure`."""

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.modules.ingestion.domain.model import ChunkDraft, Extraction


class DocumentParser(Protocol):
    async def parse(self, data: bytes, mime_type: str) -> Extraction:
        """Extracts text blocks. Raises ExtractionError for problems with the document."""
        ...


class DocumentReadyHook(Protocol):
    async def __call__(
        self, session: AsyncSession, *, document_id: uuid.UUID, content_version: int
    ) -> None:
        """Runs in the transaction that marks the document ready (e.g. to queue more work), so
        it happens only if the document really is ready."""
        ...


class ChunkWriter(Protocol):
    async def replace_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
        chunks: list[ChunkDraft],
        embeddings: list[list[float]],
    ) -> None:
        """Replaces all chunks of the document with their embeddings (same order), inside the
        caller's transaction."""
        ...
