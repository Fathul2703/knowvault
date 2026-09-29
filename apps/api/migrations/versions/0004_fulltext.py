"""Full-text search: generated chunks.content_tsv ('simple' configuration) with a GIN index.

The column is computed by PostgreSQL, so existing chunks are covered without re-processing.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30 01:12:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "content_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, content)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chunks_content_tsv", "chunks", ["content_tsv"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_content_tsv", table_name="chunks")
    op.drop_column("chunks", "content_tsv")
