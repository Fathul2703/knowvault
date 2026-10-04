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


class CommitCounter:
    """Stands in for the session: reranking first ends the read-only transaction."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class ScriptedReranker:
    """Scores chunk n (content "chunk n") with scores[n]."""

    def __init__(self, scores: dict[int, float]) -> None:
        self.scores = scores
        self.calls: list[list[str]] = []

    @property
    def model_id(self) -> str:
        return "scripted"

    async def score(self, query: str, passages: list[str]) -> list[float]:
        self.calls.append(passages)
        return [self.scores[int(passage.split()[1])] for passage in passages]


async def test_reranker_reorders_hybrid_results_and_records_scores() -> None:
    session = CommitCounter()
    reranker = ScriptedReranker({1: 0.2, 2: 0.9, 3: 0.1, 4: 0.5})
    service = SearchService(CountingEmbeddings(), MemoryIndex(), reranker, rerank_candidates=10)

    result = await service.search(cast(AsyncSession, session), query="q", scope=SCOPE, top_k=2)

    assert [hit.chunk.chunk_id.int for hit in result.hits] == [2, 4]
    assert [hit.rerank_score for hit in result.hits] == [0.9, 0.5]
    assert result.reranker == "scripted"
    # All four fused results were scored although only two were requested.
    assert len(reranker.calls[0]) == 4
    assert session.commits == 1


async def test_only_the_first_candidates_are_reranked() -> None:
    reranker = ScriptedReranker({1: 0.9, 2: 0.9, 3: 0.1, 4: 0.9})
    service = SearchService(CountingEmbeddings(), MemoryIndex(), reranker, rerank_candidates=2)

    result = await service.search(
        cast(AsyncSession, CommitCounter()), query="q", scope=SCOPE, top_k=4
    )

    # Fused order is 3, then the others; only the first two are scored. Chunk 3 scores lower
    # than its partner, the rest keep their fused order with no score.
    scored = [hit for hit in result.hits if hit.rerank_score is not None]
    assert len(scored) == 2
    assert result.hits[1].chunk.chunk_id.int == 3
    assert result.hits[2].rerank_score is None


async def test_ties_keep_the_fused_order() -> None:
    plain = await SearchService(CountingEmbeddings(), MemoryIndex()).search(
        SESSION, query="q", scope=SCOPE, top_k=4
    )
    reranker = ScriptedReranker(dict.fromkeys(range(1, 5), 0.5))
    reranked = await SearchService(CountingEmbeddings(), MemoryIndex(), reranker).search(
        cast(AsyncSession, CommitCounter()), query="q", scope=SCOPE, top_k=4
    )
    assert [h.chunk.chunk_id for h in reranked.hits] == [h.chunk.chunk_id for h in plain.hits]


@pytest.mark.parametrize("mode", [SearchMode.VECTOR, SearchMode.FULLTEXT])
async def test_single_method_modes_are_not_reranked(mode: SearchMode) -> None:
    reranker = ScriptedReranker({})
    service = SearchService(CountingEmbeddings(), MemoryIndex(), reranker)
    result = await service.search(SESSION, query="q", scope=SCOPE, top_k=3, mode=mode)
    assert reranker.calls == []
    assert result.reranker is None
    assert all(hit.rerank_score is None for hit in result.hits)
