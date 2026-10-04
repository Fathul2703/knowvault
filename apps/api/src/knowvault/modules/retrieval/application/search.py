"""Search over a user's chunks: vector, full-text, or both fused with RRF."""

import uuid
from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.reranker import Reranker
from knowvault.modules.retrieval.domain.fusion import reciprocal_rank_fusion
from knowvault.modules.retrieval.domain.model import (
    CANDIDATES_PER_LIST,
    MAX_TOP_K,
    Candidate,
    SearchHit,
    SearchMode,
    SearchScope,
)


class ChunkIndex(Protocol):
    async def vector_candidates(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        scope: SearchScope,
        embedding_model: str,
        limit: int,
    ) -> list[Candidate]:
        """Chunks closest to the query vector by cosine distance, best first.

        Only chunks embedded by `embedding_model` are considered: vectors from different
        models are not comparable.
        """
        ...

    async def fulltext_candidates(
        self, session: AsyncSession, *, query: str, scope: SearchScope, limit: int
    ) -> list[Candidate]:
        """Chunks matching the query's words, best first. Empty if the query has no words."""
        ...

    async def similarities(
        self,
        session: AsyncSession,
        *,
        chunk_ids: list[uuid.UUID],
        query_vector: list[float],
        embedding_model: str,
    ) -> dict[uuid.UUID, float]:
        """Cosine similarity of the given chunks to the query vector, where available."""
        ...


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    mode: SearchMode
    # None in full-text mode, where the query is not embedded.
    embedding_model: str | None
    # Set when hybrid results were reordered by a cross-encoder.
    reranker: str | None = None


class SearchService:
    def __init__(
        self,
        embeddings: EmbeddingModel,
        index: ChunkIndex,
        reranker: Reranker | None = None,
        rerank_candidates: int = 10,
    ) -> None:
        self._embeddings = embeddings
        self._index = index
        self._reranker = reranker
        self._rerank_candidates = rerank_candidates

    async def _rerank(
        self, reranker: Reranker, query: str, hits: list[SearchHit]
    ) -> list[SearchHit]:
        """Reorders the first `rerank_candidates` hits by cross-encoder relevance.

        Hits beyond the candidates keep their fused order after the reranked ones. Ties keep
        the fused order, so a reranker that cannot tell passages apart changes nothing.
        """
        head, tail = hits[: self._rerank_candidates], hits[self._rerank_candidates :]
        scores = await reranker.score(query, [hit.chunk.content for hit in head])
        order = sorted(range(len(head)), key=lambda i: (-scores[i], i))
        return [replace(head[i], rerank_score=scores[i]) for i in order] + tail

    async def search(
        self,
        session: AsyncSession,
        *,
        query: str,
        scope: SearchScope,
        top_k: int,
        mode: SearchMode = SearchMode.HYBRID,
    ) -> SearchResult:
        if not 1 <= top_k <= MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
        if mode is SearchMode.FULLTEXT:
            fulltext = await self._index.fulltext_candidates(
                session, query=query, scope=scope, limit=top_k
            )
            hits = [
                SearchHit(c.chunk, c.value, None, vector_rank=None, fulltext_rank=rank)
                for rank, c in enumerate(fulltext, start=1)
            ]
            return SearchResult(hits, mode, embedding_model=None)

        # Embed before touching the database, so no connection is held during inference.
        vector = await self._embeddings.embed_query(query)
        model = self._embeddings.model_id
        limit = max(CANDIDATES_PER_LIST, top_k) if mode is SearchMode.HYBRID else top_k
        by_vector = await self._index.vector_candidates(
            session, query_vector=vector, scope=scope, embedding_model=model, limit=limit
        )
        if mode is SearchMode.VECTOR:
            hits = [
                SearchHit(c.chunk, c.value, c.value, vector_rank=rank, fulltext_rank=None)
                for rank, c in enumerate(by_vector, start=1)
            ]
            return SearchResult(hits, mode, embedding_model=model)

        by_text = await self._index.fulltext_candidates(
            session, query=query, scope=scope, limit=limit
        )
        records = {c.chunk.chunk_id: c.chunk for c in (*by_vector, *by_text)}
        similarity = {c.chunk.chunk_id: c.value for c in by_vector}
        fused = reciprocal_rank_fusion(
            {
                "vector": [c.chunk.chunk_id for c in by_vector],
                "fulltext": [c.chunk.chunk_id for c in by_text],
            }
        )
        # With a reranker, more fused results than requested are scored and the best kept.
        fused = fused[: max(top_k, self._rerank_candidates) if self._reranker else top_k]

        # Chunks found only by full-text search still get a similarity, for callers that
        # need an absolute relevance signal (e.g. deciding there is not enough evidence).
        missing = [item.id for item in fused if item.id not in similarity]
        if missing:
            similarity |= await self._index.similarities(
                session, chunk_ids=missing, query_vector=vector, embedding_model=model
            )

        hits = [
            SearchHit(
                chunk=records[item.id],
                score=item.score,
                similarity=similarity.get(item.id),
                vector_rank=item.ranks.get("vector"),
                fulltext_rank=item.ranks.get("fulltext"),
            )
            for item in fused
        ]
        if self._reranker is None:
            return SearchResult(hits, mode, embedding_model=model)
        # Searching only reads: end the transaction so no connection is held while the
        # cross-encoder runs (docs/ARCHITECTURE.md §10.2).
        await session.commit()
        reranked = await self._rerank(self._reranker, query, hits)
        return SearchResult(
            reranked[:top_k], mode, embedding_model=model, reranker=self._reranker.model_id
        )
