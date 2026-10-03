"""Persistence models for conversations, messages, citations and retrieval traces."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base, TimestampMixin

_UUID_DEFAULT = text("gen_random_uuid()")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=_UUID_DEFAULT
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Empty until set by the user or taken from the first question.
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Which documents answers may use: {"collection_id": ..., "document_ids": [...]}.
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="role"),
        CheckConstraint("status IN ('streaming', 'complete', 'refused', 'error')", name="status"),
        Index("ix_messages_conversation_seq", "conversation_id", "seq"),
        # Finds answers still being written (one per user at a time).
        Index(
            "ix_messages_streaming",
            "created_at",
            postgresql_where=text("status = 'streaming'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=_UUID_DEFAULT
    )
    # Orders messages; a question and its answer are created in the same transaction and
    # would share created_at.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MessageCitation(Base):
    """A source given to the model for an answer, with a snapshot of what it said then.

    The snapshot keeps old answers readable after the document changes or is deleted; the
    links to the chunk and document are then cleared.
    """

    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    # The n of [n].
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Whether the answer cites this source.
    cited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    document_title: Mapped[str] = mapped_column(String(300), nullable=False)
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)


class RetrievalTraceRecord(Base):
    """How the sources of an answer were found. IDs, ranks and scores; no document text."""

    __tablename__ = "retrieval_traces"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    query_original: Mapped[str] = mapped_column(Text, nullable=False)
    query_rewritten: Mapped[str | None] = mapped_column(Text)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    selected_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
