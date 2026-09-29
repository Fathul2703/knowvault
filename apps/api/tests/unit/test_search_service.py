"""SearchService orchestration with an in-memory index (no database)."""

import uuid
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.adapters.embeddings import FakeEmbeddings
from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.domain.model import (
    Candidate,
    ChunkRecord,
    SearchMode,
    SearchScope,
)

SESSION = cast(AsyncSession, object())
SCOPE = SearchScope(owner_id=uuid.uuid4())


def record(n: int) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=uuid.UUID(int=n),
        document_id=uuid.UUID(int=100 + n),
        document_title=f"doc {n}",
        document_kind="file",
        ordinal=0,
        content=f"chunk {n}",
        page_start=None,
        page_end=None,
        heading_path=(),
    )


class CountingEmbeddings(FakeEmbeddings):
    def __init__(self) -> None:
        super().__init__()
        self.queries = 0

    async def embed_query(self, text: str) -> list[float]:
        self.queries += 1
        return await super().embed_query(text)


class MemoryIndex:
    """Vector list: chunks 1, 2, 3 (similarity 0.9, 0.8, 0.7). Full-text list: chunks 3, 4."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def vector_candidates(self, session: AsyncSession, **kwargs: Any) -> list[Candidate]:
        self.calls.append(("vector", kwargs["limit"]))
        return [Candidate(record(n), s) for n, s in ((1, 0.9), (2, 0.8), (3, 0.7))]

    async def fulltext_candidates(self, session: AsyncSession, **kwargs: Any) -> list[Candidate]:
        self.calls.append(("fulltext", kwargs["limit"]))
        return [Candidate(record(3), 0.5), Candidate(record(4), 0.4)]

    async def similarities(
        self, session: AsyncSession, *, chunk_ids: list[uuid.UUID], **_: Any
    ) -> dict[uuid.UUID, float]:
        self.calls.append(("similarities", sorted(chunk_ids)))
        return {chunk_id: 0.1 for chunk_id in chunk_ids}


@pytest.fixture
def parts() -> tuple[CountingEmbeddings, MemoryIndex, SearchService]:
    embeddings, index = CountingEmbeddings(), MemoryIndex()
    return embeddings, index, SearchService(embeddings, index)


async def test_hybrid_fuses_both_lists(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    _, index, service = parts
    result = await service.search(SESSION, query="q", scope=SCOPE, top_k=4)
    ids = [hit.chunk.chunk_id.int for hit in result.hits]
    assert ids[0] == 3  # the only chunk found by both methods
    assert set(ids) == {1, 2, 3, 4}
    top = result.hits[0]
    assert (top.vector_rank, top.fulltext_rank, top.similarity) == (3, 1, 0.7)
    # Candidate lists are wider than top_k.
    assert ("vector", 30) in index.calls
    assert ("fulltext", 30) in index.calls


async def test_hybrid_fills_similarity_for_fulltext_only_hits(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    _, index, service = parts
    result = await service.search(SESSION, query="q", scope=SCOPE, top_k=4)
    [only_text] = [h for h in result.hits if h.chunk.chunk_id.int == 4]
    assert only_text.similarity == 0.1
    assert only_text.vector_rank is None
    assert ("similarities", [uuid.UUID(int=4)]) in index.calls


async def test_hybrid_respects_top_k(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    _, _, service = parts
    result = await service.search(SESSION, query="q", scope=SCOPE, top_k=2)
    assert len(result.hits) == 2


async def test_fulltext_mode_does_not_embed_the_query(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    embeddings, index, service = parts
    result = await service.search(
        SESSION, query="q", scope=SCOPE, top_k=5, mode=SearchMode.FULLTEXT
    )
    assert embeddings.queries == 0
    assert result.embedding_model is None
    assert [h.fulltext_rank for h in result.hits] == [1, 2]
    assert all(h.similarity is None for h in result.hits)
    assert index.calls == [("fulltext", 5)]


async def test_vector_mode_scores_by_similarity(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    _, index, service = parts
    result = await service.search(SESSION, query="q", scope=SCOPE, top_k=3, mode=SearchMode.VECTOR)
    assert [h.score for h in result.hits] == [0.9, 0.8, 0.7]
    assert [h.vector_rank for h in result.hits] == [1, 2, 3]
    assert index.calls == [("vector", 3)]


async def test_rejects_invalid_top_k(
    parts: tuple[CountingEmbeddings, MemoryIndex, SearchService],
) -> None:
    _, _, service = parts
    with pytest.raises(ValueError, match="top_k"):
        await service.search(SESSION, query="q", scope=SCOPE, top_k=0)
