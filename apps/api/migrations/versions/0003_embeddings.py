"""Embeddings: pgvector extension, chunks.embedding vector(1024) with an HNSW index.

Chunks created before this migration have no embedding; run `knowvault reindex` to embed them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 00:06:49.250294
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Requires a role allowed to create the extension (the database owner in Compose and CI).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("embedding", Vector(1024), nullable=True))
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.add_column("documents", sa.Column("embedding_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "embedding_model")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_column("chunks", "embedding")
    # The extension is left installed: other objects may depend on it.
