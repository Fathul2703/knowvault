"""Answer evaluation: every question is answered through the production answer service.

Automatic measures only (docs/ARCHITECTURE.md §10.4): whether the system answers or refuses
when it should, whether citations point at sources it was given and at sources that contain
the labelled evidence, and whether planted instructions leak into answers. Whether a cited
source really supports its sentence is judged by people, with the review sheet.
"""

import random
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from knowvault.core.chat import ChatModels
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.core.embeddings import EmbeddingModel
from knowvault.core.reranker import Reranker
from knowvault.core.storage import ObjectStorage
from knowvault.evaluation.dataset import Question, is_relevant
from knowvault.evaluation.metrics import percentile
from knowvault.evaluation.runner import count_chunks, ingest_corpus
from knowvault.modules.assistant.application.answer import (
    AnswerDone,
    AnswerFailed,
    AnswerService,
    AnswerSettings,
    AnswerText,
    SourcesFound,
)
from knowvault.modules.assistant.application.prompts import PROMPT_VERSION
from knowvault.modules.assistant.domain.model import Source
from knowvault.modules.assistant.infrastructure.retriever import SearchRetriever
from knowvault.modules.assistant.infrastructure.store import PostgresConversationStore
from knowvault.modules.graph.infrastructure.entity_links import build_entity_links
from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.infrastructure.postgres_index import PostgresChunkIndex

# Large enough never to stop an evaluation run.
_UNLIMITED_TOKENS = 10**12
_UNLIMITED_QUESTIONS = 10**9


@dataclass(frozen=True)
class CitedSource:
    ordinal: int
    document: str
    location: str | None
    text: str
    cited: bool
    relevant: bool


@dataclass(frozen=True)
class AnswerResult:
    question_id: str
    category: str
    language: str
    answerable: bool
    status: str  # complete | refused | error
    answer: str
    cited: tuple[int, ...]
    invalid_citations: tuple[int, ...]
    sources: tuple[CitedSource, ...]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    error_code: str | None = None
    # Injection questions: whether the planted canary appears in the answer.
    canary_leaked: bool | None = None

    @property
    def evidence_in_sources(self) -> bool:
        """Whether retrieval gave the model a source containing the labelled evidence."""
        return any(source.relevant for source in self.sources)

    @property
    def cited_relevant(self) -> bool:
        """Whether a cited source contains the labelled evidence."""
        return any(source.cited and source.relevant for source in self.sources)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


@dataclass(frozen=True)
class AnswerSummary:
    questions: int
    answerable: int
    unanswerable: int
    # Answerable questions: answered, refused although answerable, failed.
    answered_rate: float | None
    false_refusal_rate: float | None
    # Unanswerable questions: refused (correct), answered anyway.
    refusal_rate: float | None
    false_answer_rate: float | None
    # Right decision (answer or refuse) over all questions; errors count as wrong.
    refusal_accuracy: float | None
    error_rate: float | None
    # Over complete answers.
    answers: int
    with_citation_rate: float | None
    invalid_citation_rate: float | None
    # Over complete answers to answerable questions.
    cited_relevant_rate: float | None
    # Over answerable questions: retrieval found the evidence (an upper bound for answering).
    evidence_in_sources_rate: float | None
    injection_questions: int
    injection_leaks: int
    latency_p50_ms: float
    latency_p95_ms: float
    input_tokens: int
    output_tokens: int
    by_category: dict[str, dict[str, float | None]] = field(default_factory=dict)


def summarize_answers(results: Sequence[AnswerResult]) -> AnswerSummary:
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    complete = [r for r in results if r.status == "complete"]
    complete_answerable = [r for r in complete if r.answerable]
    correct = sum(1 for r in answerable if r.status == "complete") + sum(
        1 for r in unanswerable if r.status == "refused"
    )
    injection = [r for r in results if r.canary_leaked is not None]
    latencies = [r.latency_ms for r in results]

    by_category: dict[str, dict[str, float | None]] = {}
    for category in sorted({r.category for r in results}):
        rows = [r for r in results if r.category == category]
        done = [r for r in rows if r.status == "complete"]
        by_category[category] = {
            "questions": len(rows),
            "answered": _rate(len(done), len(rows)),
            "refused": _rate(sum(1 for r in rows if r.status == "refused"), len(rows)),
            "cited_relevant": _rate(sum(1 for r in done if r.cited_relevant), len(done))
            if rows[0].answerable
            else None,
        }

    return AnswerSummary(
        questions=len(results),
        answerable=len(answerable),
        unanswerable=len(unanswerable),
        answered_rate=_rate(sum(1 for r in answerable if r.status == "complete"), len(answerable)),
        false_refusal_rate=_rate(
            sum(1 for r in answerable if r.status == "refused"), len(answerable)
        ),
        refusal_rate=_rate(
            sum(1 for r in unanswerable if r.status == "refused"), len(unanswerable)
        ),
        false_answer_rate=_rate(
            sum(1 for r in unanswerable if r.status == "complete"), len(unanswerable)
        ),
        refusal_accuracy=_rate(correct, len(results)),
        error_rate=_rate(sum(1 for r in results if r.status == "error"), len(results)),
        answers=len(complete),
        with_citation_rate=_rate(sum(1 for r in complete if r.cited), len(complete)),
        invalid_citation_rate=_rate(sum(1 for r in complete if r.invalid_citations), len(complete)),
        cited_relevant_rate=_rate(
            sum(1 for r in complete_answerable if r.cited_relevant), len(complete_answerable)
        ),
        evidence_in_sources_rate=_rate(
            sum(1 for r in answerable if r.evidence_in_sources), len(answerable)
        ),
        injection_questions=len(injection),
        injection_leaks=sum(1 for r in injection if r.canary_leaked),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        by_category=by_category,
    )


@dataclass
class AnswerReport:
    created_at: datetime
    config: dict[str, object]
    summary: AnswerSummary
    results: list[AnswerResult]
    questions: list[Question]


def _cited_sources(
    question: Question, sources: Sequence[Source], cited: set[int], names: dict[uuid.UUID, str]
) -> tuple[CitedSource, ...]:
    return tuple(
        CitedSource(
            ordinal=source.ordinal,
            document=names.get(source.passage.document_id, "?"),
            location=source.passage.location,
            text=source.passage.content,
            cited=source.ordinal in cited,
            relevant=question.answerable
            and is_relevant(
                question, names.get(source.passage.document_id, ""), source.passage.content
            ),
        )
        for source in sources
    )


async def answer_questions(
    *,
    service: AnswerService,
    store: PostgresConversationStore,
    owner_id: uuid.UUID,
    document_names: dict[uuid.UUID, str],
    questions: Sequence[Question],
) -> list[AnswerResult]:
    """Asks every question in a new conversation of its own, so answers are independent."""
    results: list[AnswerResult] = []
    for question in questions:
        conversation = await store.create(
            owner_id, title=question.id, collection_id=None, document_ids=()
        )
        turn = await service.start(
            owner_id=owner_id, conversation_id=conversation.id, question=question.question
        )
        sources: list[Source] = []
        text: list[str] = []
        done: AnswerDone | None = None
        failed: AnswerFailed | None = None
        async for event in service.stream(turn):
            if isinstance(event, SourcesFound):
                sources = event.sources
            elif isinstance(event, AnswerText):
                text.append(event.text)
            elif isinstance(event, AnswerDone):
                done = event
            elif isinstance(event, AnswerFailed):
                failed = event

        streamed = "".join(text)
        detail = await store.get(owner_id, conversation.id)
        stored = detail.messages[-1].message
        # The stored text is what the user keeps (the refusal text for refusals); what streamed
        # was visible too, so both are checked for leaks.
        answer = stored.content
        cited = set(done.cited) if done else set()
        results.append(
            AnswerResult(
                question_id=question.id,
                category=question.category,
                language=question.language,
                answerable=question.answerable,
                status=done.status.value if done else "error",
                answer=answer,
                cited=done.cited if done else (),
                invalid_citations=done.invalid if done else (),
                sources=_cited_sources(question, sources, cited, document_names),
                latency_ms=float(stored.latency_ms or 0),
                input_tokens=stored.prompt_tokens or 0,
                output_tokens=stored.completion_tokens or 0,
                error_code=failed.code if failed else None,
                canary_leaked=any(
                    question.canary.casefold() in shown.casefold() for shown in (answer, streamed)
                )
                if question.canary
                else None,
            )
        )
    return results


def review_sample(results: Sequence[AnswerResult], size: int, seed: int = 0) -> list[AnswerResult]:
    """Complete answers to answerable questions, sampled reproducibly for manual review."""
    candidates = [r for r in results if r.answerable and r.status == "complete"]
    if len(candidates) <= size:
        return candidates
    # Reproducible sampling, not security.
    picked = set(random.Random(seed).sample(range(len(candidates)), size))  # noqa: S311
    return [r for index, r in enumerate(candidates) if index in picked]


async def run_answer_eval(
    *,
    settings: Settings,
    database: Database,
    storage: ObjectStorage,
    embeddings: EmbeddingModel,
    models: ChatModels,
    corpus: Sequence[Path],
    questions: Sequence[Question],
    reranker: Reranker | None = None,
) -> AnswerReport:
    owner_id, names = await ingest_corpus(
        settings=settings,
        database=database,
        storage=storage,
        embeddings=embeddings,
        corpus=corpus,
    )
    store = PostgresConversationStore(
        database.sessionmaker,
        history_turns=0,
        history_chars=0,
        daily_token_limit=_UNLIMITED_TOKENS,
        questions_per_minute=_UNLIMITED_QUESTIONS,
    )
    service = AnswerService(
        store,
        SearchRetriever(
            database.sessionmaker,
            SearchService(
                embeddings,
                PostgresChunkIndex(),
                reranker,
                rerank_candidates=settings.rerank_candidates,
                entity_links=build_entity_links(settings.graph_retrieval),
            ),
        ),
        models,
        AnswerSettings(
            max_sources=settings.chat_max_sources,
            context_chars=settings.chat_context_chars,
            max_output_tokens=settings.chat_max_output_tokens,
        ),
    )
    results = await answer_questions(
        service=service,
        store=store,
        owner_id=owner_id,
        document_names=names,
        questions=questions,
    )
    return AnswerReport(
        created_at=datetime.now(UTC),
        config={
            "llm_provider": settings.llm_provider,
            "answer_model": models.answer.model_id,
            "embedding_model": embeddings.model_id,
            "reranker": reranker.model_id if reranker else None,
            "prompt_version": PROMPT_VERSION,
            "documents": len(names),
            "chunks": await count_chunks(database, owner_id),
            "questions": len(questions),
            "max_sources": settings.chat_max_sources,
            "context_chars": settings.chat_context_chars,
            "max_output_tokens": settings.chat_max_output_tokens,
        },
        summary=summarize_answers(results),
        results=results,
        questions=list(questions),
    )
