"""Persistence models for entities, their mentions in chunks, and relations."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base, TimestampMixin

_UUID_DEFAULT = text("gen_random_uuid()")
_TYPES = "'code', 'name', 'person', 'organization', 'place', 'product', 'concept'"


class Entity(TimestampMixin, Base):
    """Something a user's documents mention; one row per owner, type and normalised name."""

    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint(f"type IN ({_TYPES})", name="type"),
        UniqueConstraint("owner_id", "type", "normalized_name", name="uq_entities_owner_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=_UUID_DEFAULT
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # As first written in the documents.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)


class EntityMention(Base):
    """An entity appears in a chunk. Deleting or reprocessing the document removes it."""

    __tablename__ = "entity_mentions"
    __table_args__ = (Index("ix_entity_mentions_owner_document", "owner_id", "document_id"),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Occurrences in the chunk.
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Relation(Base):
    """Two entities related in a chunk (the evidence); `source` sorts before `target`."""

    __tablename__ = "relations"
    __table_args__ = (
        Index("ix_relations_owner_document", "owner_id", "document_id"),
        Index("ix_relations_target", "target_entity_id"),
    )

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
