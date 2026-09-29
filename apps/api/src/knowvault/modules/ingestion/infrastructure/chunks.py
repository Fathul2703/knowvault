"""Chunk persistence."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base
from knowvault.core.embeddings import EMBEDDING_DIMENSIONS
from knowvault.core.text_search import FULLTEXT_CONFIG
from knowvault.modules.ingestion.domain.model import ChunkDraft


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_ordinal"),
        # Approximate nearest-neighbour search by cosine distance.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_content_tsv", "content_tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalised from the document (it never changes) so searches can filter without a join.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    # Full-text search vector, maintained by PostgreSQL from `content`.
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed(f"to_tsvector('{FULLTEXT_CONFIG}'::regconfig, content)", persisted=True)
    )
    # Null until the chunk has been embedded (e.g. chunks created before Phase 3).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SqlChunkWriter:
    async def replace_chunks(
        self,
        session: AsyncSession,
        *,
        document_id: uuid.UUID,
        owner_id: uuid.UUID,
        chunks: list[ChunkDraft],
        embeddings: list[list[float]],
    ) -> None:
        if len(embeddings) != len(chunks):
            raise ValueError("every chunk needs exactly one embedding")
        await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        if not chunks:
            return
        await session.execute(
            insert(Chunk),
            [
                {
                    "id": uuid.uuid4(),
                    "document_id": document_id,
                    "owner_id": owner_id,
                    "ordinal": c.ordinal,
                    "content": c.content,
                    "char_count": len(c.content),
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "heading_path": list(c.heading_path),
                    "embedding": vector,
                }
                for c, vector in zip(chunks, embeddings, strict=True)
            ],
        )


async def list_chunks(
    session: AsyncSession, document_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[Sequence[Chunk], int]:
    total = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document_id)
    )
    rows = await session.scalars(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.ordinal)
        .offset(offset)
        .limit(limit)
    )
    return rows.all(), total or 0
