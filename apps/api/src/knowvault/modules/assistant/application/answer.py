"""Answering a question from the user's documents, as a stream of events."""

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import anyio

from knowvault.core.chat import ChatModelError, ChatModels, StreamEnd, TokenUsage
from knowvault.modules.assistant.application import prompts
from knowvault.modules.assistant.application.ports import (
    ConversationStore,
    RetrievalTrace,
    Retriever,
    TurnResult,
    TurnStart,
)
from knowvault.modules.assistant.domain.citations import CitationCheck, check_citations
from knowvault.modules.assistant.domain.context import select_sources
from knowvault.modules.assistant.domain.model import (
    REFUSAL_TEXT,
    MessageStatus,
    Passage,
    Source,
)
from knowvault.modules.assistant.domain.refusal import RefusalDetector, mentions_no_answer
from knowvault.modules.retrieval.domain.model import SearchHit

logger = logging.getLogger(__name__)

# A rewritten query longer than this is not a question any more; the original is used.
_MAX_CONDENSED_CHARS = 1000
_CONDENSE_MAX_TOKENS = 200


@dataclass(frozen=True)
class AnswerSettings:
    max_sources: int
    context_chars: int
    max_output_tokens: int


# --- Events, in the order they are produced ----------------------------------------------------


@dataclass(frozen=True)
class MessageCreated:
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    message_id: uuid.UUID


@dataclass(frozen=True)
class SourcesFound:
    sources: list[Source]


@dataclass(frozen=True)
class AnswerText:
    text: str


@dataclass(frozen=True)
class AnswerDone:
    message_id: uuid.UUID
    status: MessageStatus
    cited: tuple[int, ...]
    invalid: tuple[int, ...]
    usage: TokenUsage


@dataclass(frozen=True)
class AnswerFailed:
    message_id: uuid.UUID
    code: str
    detail: str


AnswerEvent = MessageCreated | SourcesFound | AnswerText | AnswerDone | AnswerFailed


def _passage(hit: SearchHit) -> Passage:
    chunk = hit.chunk
    return Passage(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_title=chunk.document_title,
        ordinal=chunk.ordinal,
        content=chunk.content,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        heading_path=chunk.heading_path,
    )


def _candidate(hit: SearchHit) -> dict[str, object]:
    return {
        "chunk_id": str(hit.chunk.chunk_id),
        "document_id": str(hit.chunk.document_id),
        "score": round(hit.score, 6),
        "similarity": None if hit.similarity is None else round(hit.similarity, 6),
        "vector_rank": hit.vector_rank,
        "fulltext_rank": hit.fulltext_rank,
    }


class AnswerService:
    """Implements docs/ARCHITECTURE.md §10.1.

    Starting a turn and streaming its answer are separate steps, so that a missing
    conversation or a spent quota is an ordinary HTTP error before any stream begins. No
    database connection is held while the model writes.
    """

    def __init__(
        self,
        store: ConversationStore,
        retriever: Retriever,
        models: ChatModels,
        settings: AnswerSettings,
    ) -> None:
        self._store = store
        self._retriever = retriever
        self._models = models
        self._settings = settings

    async def start(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID, question: str
    ) -> TurnStart:
        return await self._store.start_turn(
            owner_id=owner_id, conversation_id=conversation_id, question=question
        )

    async def _condense(self, turn: TurnStart) -> tuple[str, TokenUsage]:
        """A standalone search query for a follow-up question."""
        completion = await self._models.fast.complete(
            system=prompts.CONDENSE_SYSTEM,
            messages=prompts.condense_messages(turn.history, turn.question),
            max_tokens=_CONDENSE_MAX_TOKENS,
        )
        query = prompts.normalize_question(completion.text)
        if not query or len(query) > _MAX_CONDENSED_CHARS:
            return turn.question, completion.usage
        return query, completion.usage

    async def stream(self, turn: TurnStart) -> AsyncGenerator[AnswerEvent]:
        started = time.monotonic()
        usage = TokenUsage()
        sources: list[Source] = []
        trace: RetrievalTrace | None = None
        written: list[str] = []
        result: TurnResult | None = None
        failure: AnswerFailed | None = None
        model_id: str | None = None

        def finished(status: MessageStatus, content: str, error: str | None = None) -> TurnResult:
            complete = status is MessageStatus.COMPLETE
            return TurnResult(
                status=status,
                content=content,
                model_id=model_id,
                usage=usage,
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code=error,
                sources=sources,
                cited=check_citations(content, len(sources)).cited if complete else (),
                trace=trace,
            )

        yield MessageCreated(turn.conversation_id, turn.user_message_id, turn.assistant_message_id)
        try:
            query = turn.question
            if turn.history:
                query, condense_usage = await self._condense(turn)
                usage += condense_usage
            hits = await self._retriever.retrieve(
                query, scope=turn.scope, top_k=self._settings.max_sources * 2
            )
            sources = select_sources(
                [_passage(hit) for hit in hits],
                max_sources=self._settings.max_sources,
                max_chars=self._settings.context_chars,
            )
            trace = RetrievalTrace(
                query_original=turn.question,
                query_rewritten=query if query != turn.question else None,
                candidates=[_candidate(hit) for hit in hits],
                selected_chunk_ids=[source.passage.chunk_id for source in sources],
                params={
                    "prompt_version": prompts.PROMPT_VERSION,
                    "top_k": self._settings.max_sources * 2,
                    "max_sources": self._settings.max_sources,
                    "context_chars": self._settings.context_chars,
                },
            )
            yield SourcesFound(sources)

            if not sources:
                # Nothing to ground an answer in: refuse without calling the model.
                written.append(REFUSAL_TEXT)
                yield AnswerText(REFUSAL_TEXT)
                result = finished(MessageStatus.REFUSED, REFUSAL_TEXT)
            else:
                model_id = self._models.answer.model_id
                detector = RefusalDetector()
                async for event in self._models.answer.stream(
                    system=prompts.ANSWER_SYSTEM,
                    messages=prompts.answer_messages(turn.history, turn.question, sources),
                    max_tokens=self._settings.max_output_tokens,
                ):
                    if isinstance(event, StreamEnd):
                        usage += event.usage
                        continue
                    if text := detector.feed(event.text):
                        written.append(text)
                        yield AnswerText(text)
                if tail := detector.finish():
                    written.append(tail)
                    yield AnswerText(tail)
                answer = "".join(written)
                if detector.refused or mentions_no_answer(answer):
                    if not written:
                        yield AnswerText(REFUSAL_TEXT)
                    result = finished(MessageStatus.REFUSED, REFUSAL_TEXT)
                else:
                    result = finished(MessageStatus.COMPLETE, answer)
        except ChatModelError as exc:
            logger.warning("answer_failed", extra={"code": exc.code})
            failure = AnswerFailed(turn.assistant_message_id, exc.code, exc.detail)
            result = finished(MessageStatus.ERROR, "".join(written), exc.code)
        except Exception:
            logger.exception("answer_failed")
            failure = AnswerFailed(
                turn.assistant_message_id, "internal_error", "The answer could not be completed."
            )
            result = finished(MessageStatus.ERROR, "".join(written), "internal_error")
        finally:
            # Also runs when the client disconnects and the stream is cancelled: what was
            # written so far is kept and the answer is marked as failed.
            with anyio.CancelScope(shield=True):
                await self._store.finish_turn(
                    turn,
                    result
                    or finished(MessageStatus.ERROR, "".join(written), "client_disconnected"),
                )

        if failure is not None:
            yield failure
            return
        check = (
            check_citations(result.content, len(sources))
            if result.status is MessageStatus.COMPLETE
            else CitationCheck((), ())
        )
        yield AnswerDone(
            turn.assistant_message_id, result.status, check.cited, check.invalid, result.usage
        )
