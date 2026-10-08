"""Knowledge graph: entities, their mentions in chunks, and relations between them.

Mentions and relations cascade with their chunks, so reprocessing or deleting a document removes
what was extracted from it.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08 14:48:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('code', 'name', 'person', 'organization', 'place', 'product', 'concept')",
            name=op.f("ck_entities_type"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_entities_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entities")),
        sa.UniqueConstraint("owner_id", "type", "normalized_name", name="uq_entities_owner_key"),
    )
    op.create_table(
        "entity_mentions",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_entity_mentions_chunk_id_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_entity_mentions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name=op.f("fk_entity_mentions_entity_id_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_entity_mentions_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entity_id", "chunk_id", name=op.f("pk_entity_mentions")),
    )
    op.create_index(
        op.f("ix_entity_mentions_chunk_id"), "entity_mentions", ["chunk_id"], unique=False
    )
    op.create_index(
        "ix_entity_mentions_owner_document",
        "entity_mentions",
        ["owner_id", "document_id"],
        unique=False,
    )
    op.create_table(
        "relations",
        sa.Column("source_entity_id", sa.UUID(), nullable=False),
        sa.Column("target_entity_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_relations_chunk_id_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_relations_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_relations_owner_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_entity_id"],
            ["entities.id"],
            name=op.f("fk_relations_source_entity_id_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_entity_id"],
            ["entities.id"],
            name=op.f("fk_relations_target_entity_id_entities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "source_entity_id", "target_entity_id", "type", "chunk_id", name=op.f("pk_relations")
        ),
    )
    op.create_index(op.f("ix_relations_chunk_id"), "relations", ["chunk_id"], unique=False)
    op.create_index(
        "ix_relations_owner_document", "relations", ["owner_id", "document_id"], unique=False
    )
    op.create_index("ix_relations_target", "relations", ["target_entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_relations_target", table_name="relations")
    op.drop_index("ix_relations_owner_document", table_name="relations")
    op.drop_index(op.f("ix_relations_chunk_id"), table_name="relations")
    op.drop_table("relations")
    op.drop_index("ix_entity_mentions_owner_document", table_name="entity_mentions")
    op.drop_index(op.f("ix_entity_mentions_chunk_id"), table_name="entity_mentions")
    op.drop_table("entity_mentions")
    op.drop_table("entities")
