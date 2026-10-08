"""Entity resolution: name embeddings on entities, and aliases merged into an entity.

Entities keep their keys; keys of names now ignore hyphens and English plurals (ADR 0016), which
applies as documents are extracted again (`knowvault extract-graph`).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 16:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entity_aliases",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("similarity", sa.Double(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name=op.f("fk_entity_aliases_entity_id_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_entity_aliases_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "owner_id", "type", "normalized_name", name=op.f("pk_entity_aliases")
        ),
    )
    op.create_index(
        op.f("ix_entity_aliases_entity_id"), "entity_aliases", ["entity_id"], unique=False
    )
    op.add_column("entities", sa.Column("embedding", Vector(1024), nullable=True))
    op.add_column("entities", sa.Column("embedding_model", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("entities", "embedding_model")
    op.drop_column("entities", "embedding")
    op.drop_index(op.f("ix_entity_aliases_entity_id"), table_name="entity_aliases")
    op.drop_table("entity_aliases")
