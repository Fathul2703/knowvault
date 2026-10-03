"""Assistant: conversations, messages, citation snapshots and retrieval traces.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03 14:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_conversations_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_owner_updated", "conversations", ["owner_id", "updated_at"], unique=False
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_messages_role")),
        sa.CheckConstraint(
            "status IN ('streaming', 'complete', 'refused', 'error')",
            name=op.f("ck_messages_status"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_seq", "messages", ["conversation_id", "seq"], unique=False
    )
    op.create_index(
        "ix_messages_streaming",
        "messages",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'streaming'"),
    )

    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("cited", sa.Boolean(), nullable=False),
        sa.Column("chunk_id", sa.UUID(), nullable=True),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("document_title", sa.String(length=300), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("heading_path", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name=op.f("fk_message_citations_chunk_id_chunks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_message_citations_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_citations_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", "ordinal", name=op.f("pk_message_citations")),
    )
    # Deleting or reprocessing a document clears these links; the indexes keep that fast.
    op.create_index(
        op.f("ix_message_citations_chunk_id"), "message_citations", ["chunk_id"], unique=False
    )
    op.create_index(
        op.f("ix_message_citations_document_id"),
        "message_citations",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "retrieval_traces",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("query_original", sa.Text(), nullable=False),
        sa.Column("query_rewritten", sa.Text(), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_chunk_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_retrieval_traces_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_retrieval_traces")),
    )


def downgrade() -> None:
    op.drop_table("retrieval_traces")
    op.drop_index(op.f("ix_message_citations_document_id"), table_name="message_citations")
    op.drop_index(op.f("ix_message_citations_chunk_id"), table_name="message_citations")
    op.drop_table("message_citations")
    op.drop_index("ix_messages_streaming", table_name="messages")
    op.drop_index("ix_messages_conversation_seq", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_owner_updated", table_name="conversations")
    op.drop_table("conversations")
