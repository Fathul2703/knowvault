"""Persistence models for collections, documents and notes."""

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base, TimestampMixin

_UUID_DEFAULT = text("gen_random_uuid()")

KIND_FILE = "file"
KIND_NOTE = "note"

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_collections_owner_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=_UUID_DEFAULT
    )
    # Indexed through uq_collections_owner_name, whose first column is owner_id.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class Document(TimestampMixin, Base):
    """A source of knowledge: an uploaded file or a note."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("kind IN ('file', 'note')", name="kind"),
        CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name="status"),
        CheckConstraint(
            "kind = 'note' OR (storage_key IS NOT NULL AND sha256 IS NOT NULL)",
            name="file_has_content",
        ),
        # The same file is stored once per user.
        Index(
            "uq_documents_owner_sha256",
            "owner_id",
            "sha256",
            unique=True,
            postgresql_where=text("kind = 'file'"),
        ),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        Index("ix_documents_owner_collection", "owner_id", "collection_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=_UUID_DEFAULT
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collections.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_PENDING)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    # Incremented whenever the content changes; processing results for older versions are
    # discarded.
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Note(Base):
    """The editable body of a document with kind 'note'."""

    __tablename__ = "notes"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
