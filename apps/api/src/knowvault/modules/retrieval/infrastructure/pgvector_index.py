"""VectorIndex backed by pgvector's HNSW index.

Retrieval reads the `chunks` and `documents` tables but does not import the ingestion or
library ORM models: the table layout is the contract, declared here as lightweight read-only
table definitions.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text, column, select, table, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core.embeddings import EMBEDDING_DIMENSIONS
from knowvault.modules.retrieval.domain.model import SearchHit, SearchScope

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


class PgVectorIndex:
    async def nearest(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        scope: SearchScope,
        embedding_model: str,
        top_k: int,
    ) -> list[SearchHit]:
        distance = _chunks.c.embedding.cosine_distance(query_vector)
        query = (
            select(
                _chunks.c.id,
                _chunks.c.document_id,
                _documents.c.title,
                _documents.c.kind,
                _chunks.c.ordinal,
                _chunks.c.content,
                _chunks.c.page_start,
                _chunks.c.page_end,
                _chunks.c.heading_path,
                (1 - distance).label("score"),
            )
            .select_from(_chunks.join(_documents, _documents.c.id == _chunks.c.document_id))
            .where(
                # Owner filter on both tables: chunks.owner_id is indexed, documents.owner_id
                # guards against any inconsistency between the two.
                _chunks.c.owner_id == scope.owner_id,
                _documents.c.owner_id == scope.owner_id,
                _documents.c.status == "ready",
                _documents.c.embedding_model == embedding_model,
                _chunks.c.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(top_k)
        )
        if scope.collection_id is not None:
            query = query.where(_documents.c.collection_id == scope.collection_id)
        if scope.document_ids:
            query = query.where(_chunks.c.document_id.in_(scope.document_ids))

        # Filters are applied after the approximate index scan. Iterative scanning (pgvector
        # 0.8+) keeps scanning until enough rows pass the filters, so a user whose chunks are
        # a small share of the index still gets `top_k` results. SET LOCAL lasts for this
        # transaction only.
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {_EF_SEARCH}"))
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        rows = (await session.execute(query)).all()
        await session.commit()
        return [
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.title,
                document_kind=row.kind,
                ordinal=row.ordinal,
                content=row.content,
                page_start=row.page_start,
                page_end=row.page_end,
                heading_path=tuple(row.heading_path),
                score=float(row.score),
            )
            for row in rows
        ]
