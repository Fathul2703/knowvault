"""Semantic search over a user's chunks."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core.embeddings import EmbeddingModel
from knowvault.modules.retrieval.domain.model import MAX_TOP_K, SearchHit, SearchScope


class VectorIndex(Protocol):
    async def nearest(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        scope: SearchScope,
        embedding_model: str,
        top_k: int,
    ) -> list[SearchHit]:
        """The `top_k` chunks closest to `query_vector` by cosine distance, best first.

        Only chunks embedded by `embedding_model` are considered: vectors from different
        models are not comparable.
        """
        ...


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    embedding_model: str


class SearchService:
    def __init__(self, embeddings: EmbeddingModel, index: VectorIndex) -> None:
        self._embeddings = embeddings
        self._index = index

    async def search(
        self, session: AsyncSession, *, query: str, scope: SearchScope, top_k: int
    ) -> SearchResult:
        if not 1 <= top_k <= MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
        # Embed before touching the database, so no connection is held during inference.
        vector = await self._embeddings.embed_query(query)
        hits = await self._index.nearest(
            session,
            query_vector=vector,
            scope=scope,
            embedding_model=self._embeddings.model_id,
            top_k=top_k,
        )
        return SearchResult(hits=hits, embedding_model=self._embeddings.model_id)
