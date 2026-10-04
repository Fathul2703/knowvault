"""Runs the retrieval evaluation against a database through the production code paths.

The corpus is uploaded with the library service and processed by the worker pipeline (parse →
chunk → embed), then every question is searched in every mode with the search service.
"""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.reranker import Reranker
from knowvault.core.storage import ObjectStorage
from knowvault.evaluation.dataset import Question, is_relevant
from knowvault.evaluation.metrics import first_relevant_rank, mrr_at, percentile, success_at
from knowvault.modules.identity.credentials import hash_password, new_token
from knowvault.modules.identity.models import User
from knowvault.modules.ingestion.domain.chunking import ChunkingConfig
from knowvault.modules.ingestion.infrastructure.chunks import Chunk
from knowvault.modules.library.models import STATUS_READY, Document
from knowvault.modules.library.service import LibraryService
from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.domain.fusion import RRF_K
from knowvault.modules.retrieval.domain.model import CANDIDATES_PER_LIST, SearchMode, SearchScope
from knowvault.modules.retrieval.infrastructure.postgres_index import PostgresChunkIndex
from knowvault.worker import build_pipeline, run_once

CUTOFFS = (1, 5, 10)


class CorpusIngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuestionResult:
    question_id: str
    category: str
    mode: str
    # 1-based rank of the first relevant chunk; None if absent from the top k (or unanswerable).
    rank: int | None
    latency_ms: float
    top_similarity: float | None
    relevant_similarity: float | None
    top_documents: tuple[str, ...]
    # Cross-encoder scores (hybrid mode with a reranker only).
    top_rerank_score: float | None = None
    relevant_rerank_score: float | None = None


@dataclass(frozen=True)
class ModeSummary:
    mode: str
    questions: int
    success: dict[int, float]
    mrr: float
    latency_p50_ms: float
    latency_p95_ms: float
    by_category: dict[str, dict[str, float]]


@dataclass
class EvalReport:
    created_at: datetime
    config: dict[str, object]
    summaries: list[ModeSummary]
    results: list[QuestionResult]
    questions: list[Question]
    similarity: dict[str, list[float]] = field(default_factory=dict)


async def ingest_corpus(
    *,
    settings: Settings,
    database: Database,
    storage: ObjectStorage,
    embeddings: EmbeddingModel,
    corpus: Sequence[Path],
) -> tuple[uuid.UUID, dict[uuid.UUID, str]]:
    """Uploads the corpus as a fresh user and processes it. Returns owner id and id → file."""
    owner_id = uuid.uuid4()
    async with database.sessionmaker() as session:
        session.add(
            User(
                id=owner_id,
                email=f"eval-{owner_id.hex[:8]}@example.invalid",
                display_name="Retrieval evaluation",
                password_hash=hash_password(new_token()),
            )
        )
        await session.commit()

    names: dict[uuid.UUID, str] = {}
    for path in corpus:
        async with database.sessionmaker() as session:
            library = LibraryService(session, settings, storage)
            with path.open("rb") as handle:
                document = await library.upload(
                    owner_id,
                    UploadFile(file=handle, filename=path.name),
                    title=None,
                    collection_id=None,
                )
            names[document.id] = path.name

    # The worker must read from the same storage the corpus was uploaded to.
    pipeline = build_pipeline(settings, database, embeddings, storage)
    while await run_once(database, pipeline, settings):
        pass

    async with database.sessionmaker() as session:
        failed = (
            await session.execute(
                select(Document.original_filename, Document.error_code).where(
                    Document.owner_id == owner_id, Document.status != STATUS_READY
                )
            )
        ).all()
    if failed:
        raise CorpusIngestionError(f"documents not processed: {failed}")
    return owner_id, names


async def evaluate(
    *,
    database: Database,
    embeddings: EmbeddingModel,
    owner_id: uuid.UUID,
    document_names: dict[uuid.UUID, str],
    questions: Sequence[Question],
    modes: Sequence[SearchMode],
    top_k: int,
    reranker: Reranker | None = None,
    rerank_candidates: int = 10,
) -> list[QuestionResult]:
    service = SearchService(
        embeddings, PostgresChunkIndex(), reranker, rerank_candidates=rerank_candidates
    )
    scope = SearchScope(owner_id=owner_id)
    results: list[QuestionResult] = []
    for mode in modes:
        for question in questions:
            started = time.perf_counter()
            async with database.sessionmaker() as session:
                found = await service.search(
                    session, query=question.question, scope=scope, top_k=top_k, mode=mode
                )
            latency_ms = (time.perf_counter() - started) * 1000
            relevance = [
                is_relevant(question, document_names[hit.chunk.document_id], hit.chunk.content)
                for hit in found.hits
            ]
            rank = first_relevant_rank(relevance)
            results.append(
                QuestionResult(
                    question_id=question.id,
                    category=question.category,
                    mode=mode.value,
                    rank=rank,
                    latency_ms=latency_ms,
                    top_similarity=found.hits[0].similarity if found.hits else None,
                    relevant_similarity=found.hits[rank - 1].similarity if rank else None,
                    top_documents=tuple(
                        document_names[hit.chunk.document_id] for hit in found.hits[:3]
                    ),
                    top_rerank_score=found.hits[0].rerank_score if found.hits else None,
                    relevant_rerank_score=found.hits[rank - 1].rerank_score if rank else None,
                )
            )
    return results


def summarize(
    results: Sequence[QuestionResult], questions: Sequence[Question], modes: Sequence[SearchMode]
) -> list[ModeSummary]:
    answerable = {q.id for q in questions if q.answerable}
    summaries = []
    for mode in modes:
        rows = [r for r in results if r.mode == mode.value and r.question_id in answerable]
        ranks = [r.rank for r in rows]
        latencies = [r.latency_ms for r in results if r.mode == mode.value]
        by_category: dict[str, dict[str, float]] = {}
        for category in sorted({r.category for r in rows}):
            category_ranks = [r.rank for r in rows if r.category == category]
            by_category[category] = {
                "questions": len(category_ranks),
                **{f"success@{k}": success_at(category_ranks, k) for k in CUTOFFS},
                "mrr@10": mrr_at(category_ranks, 10),
            }
        summaries.append(
            ModeSummary(
                mode=mode.value,
                questions=len(rows),
                success={k: success_at(ranks, k) for k in CUTOFFS},
                mrr=mrr_at(ranks, 10),
                latency_p50_ms=percentile(latencies, 50),
                latency_p95_ms=percentile(latencies, 95),
                by_category=by_category,
            )
        )
    return summaries


def similarity_distributions(results: Sequence[QuestionResult]) -> dict[str, list[float]]:
    """Cosine similarities (hybrid mode) that inform an evidence threshold for answering.

    `relevant`: similarity of the first relevant chunk of answerable questions.
    `unanswerable_top`: best similarity returned for questions the corpus cannot answer.
    """
    hybrid = [r for r in results if r.mode == SearchMode.HYBRID.value]
    reranked = {
        "rerank_relevant": sorted(
            r.relevant_rerank_score for r in hybrid if r.relevant_rerank_score is not None
        ),
        "rerank_unanswerable_top": sorted(
            r.top_rerank_score
            for r in hybrid
            if r.category == "unanswerable" and r.top_rerank_score is not None
        ),
    }
    return {
        **{name: values for name, values in reranked.items() if values},
        "relevant": sorted(
            r.relevant_similarity for r in hybrid if r.relevant_similarity is not None
        ),
        "unanswerable_top": sorted(
            r.top_similarity
            for r in hybrid
            if r.category == "unanswerable" and r.top_similarity is not None
        ),
    }


async def count_chunks(database: Database, owner_id: uuid.UUID) -> int:
    async with database.sessionmaker() as session:
        total = await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.owner_id == owner_id)
        )
    return total or 0


async def run_retrieval_eval(
    *,
    settings: Settings,
    database: Database,
    storage: ObjectStorage,
    embeddings: EmbeddingModel,
    corpus: Sequence[Path],
    questions: Sequence[Question],
    modes: Sequence[SearchMode] = tuple(SearchMode),
    top_k: int = 10,
    reranker: Reranker | None = None,
    rerank_candidates: int = 10,
) -> EvalReport:
    owner_id, names = await ingest_corpus(
        settings=settings,
        database=database,
        storage=storage,
        embeddings=embeddings,
        corpus=corpus,
    )
    results = await evaluate(
        database=database,
        embeddings=embeddings,
        owner_id=owner_id,
        document_names=names,
        questions=questions,
        modes=modes,
        top_k=top_k,
        reranker=reranker,
        rerank_candidates=rerank_candidates,
    )
    chunking = ChunkingConfig(
        target_chars=settings.chunk_target_chars,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    return EvalReport(
        created_at=datetime.now(UTC),
        config={
            "embedding_model": embeddings.model_id,
            "reranker": reranker.model_id if reranker else None,
            "rerank_candidates": rerank_candidates if reranker else None,
            "documents": len(names),
            "chunks": await count_chunks(database, owner_id),
            "questions": len(questions),
            "answerable_questions": sum(1 for q in questions if q.answerable),
            "top_k": top_k,
            "chunk_target_chars": chunking.target_chars,
            "chunk_max_chars": chunking.max_chars,
            "chunk_overlap_chars": chunking.overlap_chars,
            "rrf_k": RRF_K,
            "candidates_per_list": CANDIDATES_PER_LIST,
        },
        summaries=summarize(results, questions, modes),
        results=list(results),
        questions=list(questions),
        similarity=similarity_distributions(results),
    )
