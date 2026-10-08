"""What graph extraction needs: an extractor and storage."""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.modules.graph.domain.model import ChunkGraph, ChunkText


class EntityExtractor(Protocol):
    @property
    def name(self) -> str: ...

    async def extract(self, chunks: list[ChunkText]) -> list[ChunkGraph]:
        """Entities and relations of each chunk, in the order given."""
        ...


@dataclass(frozen=True)
class DocumentChunks:
    document_id: uuid.UUID
    owner_id: uuid.UUID
    content_version: int
    chunks: list[ChunkText]


@dataclass(frozen=True)
class GraphCounts:
    entities: int
    mentions: int
    relations: int


class GraphStore(Protocol):
    async def load_document(
        self, session: AsyncSession, document_id: uuid.UUID, content_version: int
    ) -> DocumentChunks | None:
        """The chunks of a ready document at this version; None if it changed or is gone."""
        ...

    async def lock_current(
        self, session: AsyncSession, document_id: uuid.UUID, content_version: int
    ) -> bool:
        """Locks the document row; True if it is still ready at this version."""
        ...

    async def replace_document_graph(
        self, session: AsyncSession, document: DocumentChunks, graphs: list[ChunkGraph]
    ) -> GraphCounts:
        """Replaces what was extracted from the document, inside the caller's transaction."""
        ...
