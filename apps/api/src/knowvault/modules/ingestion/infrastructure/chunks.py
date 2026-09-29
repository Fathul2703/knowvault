"""Chunk persistence."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base
from knowvault.modules.ingestion.domain.model import ChunkDraft


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_ordinal"),
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
    ) -> None:
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
                }
                for c in chunks
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
