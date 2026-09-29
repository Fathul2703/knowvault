"""ChunkIndex backed by PostgreSQL: pgvector HNSW for vectors, a GIN index for full text.

Retrieval reads the `chunks` and `documents` tables but does not import the ingestion or
library ORM models: the table layout is the contract, declared here as lightweight read-only
table definitions.
"""

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Row, Select, Text, column, func, literal, select, table, text
from sqlalchemy.dialects.postgresql import ARRAY, REGCONFIG, TSVECTOR, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core.embeddings import EMBEDDING_DIMENSIONS
from knowvault.core.text_search import FULLTEXT_CONFIG
from knowvault.modules.retrieval.domain.model import Candidate, ChunkRecord, SearchScope

_chunks = table(
    "chunks",
    column("id", UUID(as_uuid=True)),
    column("document_id", UUID(as_uuid=True)),
    column("owner_id", UUID(as_uuid=True)),
    column("ordinal"),
    column("content"),
    column("page_start"),
    column("page_end"),
    column("heading_path", ARRAY(Text)),
    column("content_tsv", TSVECTOR),
    column("embedding", Vector(EMBEDDING_DIMENSIONS)),
)
_documents = table(
    "documents",
    column("id", UUID(as_uuid=True)),
    column("owner_id", UUID(as_uuid=True)),
    column("collection_id", UUID(as_uuid=True)),
    column("title"),
    column("kind"),
    column("status"),
    column("embedding_model"),
)

# Candidates the HNSW graph explores per query; higher = better recall, slower.
_EF_SEARCH = 100
# ts_rank_cd normalisation 32 maps the rank into [0, 1): rank / (rank + 1).
_RANK_NORMALIZATION = 32


def _scoped(query: Select[Any], scope: SearchScope) -> Select[Any]:
    """Restricts a query over chunks ⋈ documents to the owner's ready documents in scope."""
    query = query.where(
        # Owner filter on both tables: chunks.owner_id is indexed, documents.owner_id guards
        # against any inconsistency between the two.
        _chunks.c.owner_id == scope.owner_id,
        _documents.c.owner_id == scope.owner_id,
        _documents.c.status == "ready",
    )
    if scope.collection_id is not None:
        query = query.where(_documents.c.collection_id == scope.collection_id)
    if scope.document_ids:
        query = query.where(_chunks.c.document_id.in_(scope.document_ids))
    return query


def _select_record(*extra: Any) -> Select[Any]:
    return select(
        _chunks.c.id,
        _chunks.c.document_id,
        _documents.c.title,
        _documents.c.kind,
        _chunks.c.ordinal,
        _chunks.c.content,
        _chunks.c.page_start,
        _chunks.c.page_end,
        _chunks.c.heading_path,
        *extra,
    ).select_from(_chunks.join(_documents, _documents.c.id == _chunks.c.document_id))


def _candidate(row: Row[Any]) -> Candidate:
    return Candidate(
        chunk=ChunkRecord(
            chunk_id=row.id,
            document_id=row.document_id,
            document_title=row.title,
            document_kind=row.kind,
            ordinal=row.ordinal,
            content=row.content,
            page_start=row.page_start,
            page_end=row.page_end,
            heading_path=tuple(row.heading_path),
        ),
        value=float(row.value),
    )


class PostgresChunkIndex:
    async def vector_candidates(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        scope: SearchScope,
        embedding_model: str,
        limit: int,
    ) -> list[Candidate]:
        distance = _chunks.c.embedding.cosine_distance(query_vector)
        query = _scoped(_select_record((1 - distance).label("value")), scope).where(
            _documents.c.embedding_model == embedding_model,
            _chunks.c.embedding.is_not(None),
        )
        # Filters are applied after the approximate index scan. Iterative scanning (pgvector
        # 0.8+) keeps scanning until enough rows pass them, so a user whose chunks are a small
        # share of the index still gets `limit` results. SET LOCAL lasts for this transaction.
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {_EF_SEARCH}"))
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        rows = await session.execute(query.order_by(distance).limit(limit))
        return [_candidate(row) for row in rows]

    async def fulltext_candidates(
        self, session: AsyncSession, *, query: str, scope: SearchScope, limit: int
    ) -> list[Candidate]:
        # websearch_to_tsquery accepts free text ("quoted phrases", -exclusions, OR) and never
        # raises a syntax error on user input.
        tsquery = func.websearch_to_tsquery(literal(FULLTEXT_CONFIG, REGCONFIG), query)
        rank = func.ts_rank_cd(_chunks.c.content_tsv, tsquery, _RANK_NORMALIZATION)
        statement = _scoped(_select_record(rank.label("value")), scope).where(
            _chunks.c.content_tsv.op("@@")(tsquery)
        )
        rows = await session.execute(statement.order_by(rank.desc(), _chunks.c.id).limit(limit))
        return [_candidate(row) for row in rows]

    async def similarities(
        self,
        session: AsyncSession,
        *,
        chunk_ids: list[uuid.UUID],
        query_vector: list[float],
        embedding_model: str,
    ) -> dict[uuid.UUID, float]:
        if not chunk_ids:
            return {}
        distance = _chunks.c.embedding.cosine_distance(query_vector)
        rows = await session.execute(
            select(_chunks.c.id, (1 - distance).label("value"))
            .select_from(_chunks.join(_documents, _documents.c.id == _chunks.c.document_id))
            .where(
                _chunks.c.id.in_(chunk_ids),
                _chunks.c.embedding.is_not(None),
                _documents.c.embedding_model == embedding_model,
            )
        )
        return {row.id: float(row.value) for row in rows}
