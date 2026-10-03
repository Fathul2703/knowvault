"""Answer orchestration with in-memory storage, search and a scripted model."""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest

from knowvault.core.chat import (
    ChatMessage,
    ChatModelError,
    ChatModels,
    Completion,
    StreamEnd,
    TextDelta,
    TokenUsage,
)
from knowvault.modules.assistant.application.answer import (
    AnswerDone,
    AnswerEvent,
    AnswerFailed,
    AnswerService,
    AnswerSettings,
    AnswerText,
    MessageCreated,
    SourcesFound,
)
from knowvault.modules.assistant.application.ports import TurnResult, TurnStart
from knowvault.modules.assistant.domain.model import REFUSAL_TEXT, MessageStatus, Turn
from knowvault.modules.retrieval.domain.model import ChunkRecord, SearchHit, SearchScope

OWNER = uuid.uuid4()


class ScriptedModel:
    """Streams the given pieces; raises `fail` after them when set."""

    def __init__(
        self,
        pieces: list[str],
        *,
        fail: Exception | None = None,
        completion: str = "",
        model_id: str = "scripted",
    ) -> None:
        self.pieces = pieces
        self.fail = fail
        self.completion = completion
        self.calls: list[list[ChatMessage]] = []
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    async def stream(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[TextDelta | StreamEnd]:
        self.calls.append(messages)
        for piece in self.pieces:
            await asyncio.sleep(0)
            yield TextDelta(piece)
        if self.fail is not None:
            raise self.fail
        yield StreamEnd(TokenUsage(100, 10), "end_turn")

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> Completion:
        self.calls.append(messages)
        return Completion(self.completion, TokenUsage(20, 5))


class MemoryStore:
    def __init__(self) -> None:
        self.finished: list[TurnResult] = []

    async def start_turn(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID, question: str
    ) -> TurnStart:
        raise NotImplementedError

    async def finish_turn(self, turn: TurnStart, result: TurnResult) -> None:
        self.finished.append(result)


class ListRetriever:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.queries: list[str] = []

    async def retrieve(self, query: str, *, scope: SearchScope, top_k: int) -> list[SearchHit]:
        self.queries.append(query)
        return self.hits


def hit(content: str, ordinal: int = 0) -> SearchHit:
    chunk = ChunkRecord(
        chunk_id=uuid.uuid4(),
        document_id=uuid.UUID(int=1),
        document_title="Leave policy",
        document_kind="note",
        ordinal=ordinal,
        content=content,
        page_start=None,
        page_end=None,
        heading_path=(),
    )
    return SearchHit(chunk, 0.03, 0.6, vector_rank=1, fulltext_rank=1)


def turn(history: list[Turn] | None = None) -> TurnStart:
    return TurnStart(
        conversation_id=uuid.uuid4(),
        owner_id=OWNER,
        user_message_id=uuid.uuid4(),
        assistant_message_id=uuid.uuid4(),
        question="How many days of leave?",
        scope=SearchScope(owner_id=OWNER),
        history=history or [],
    )


def service(
    model: ScriptedModel,
    hits: list[SearchHit],
    *,
    fast: ScriptedModel | None = None,
) -> tuple[AnswerService, MemoryStore, ListRetriever]:
    store = MemoryStore()
    retriever = ListRetriever(hits)
    models = ChatModels(answer=model, fast=fast or ScriptedModel([]))
    settings = AnswerSettings(max_sources=8, context_chars=10_000, max_output_tokens=500)
    return AnswerService(store, retriever, models, settings), store, retriever


async def events_of(service: AnswerService, start: TurnStart) -> list[AnswerEvent]:
    return [event async for event in service.stream(start)]


def text_of(events: list[AnswerEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, AnswerText))


async def test_answer_streams_in_contract_order_and_is_stored() -> None:
    model = ScriptedModel(["Twelve days ", "[1]", " per year [3]."])
    answers, store, _ = service(model, [hit("Twelve days of leave per year.")])

    events = await events_of(answers, turn())

    assert [type(e) for e in events[:2]] == [MessageCreated, SourcesFound]
    assert isinstance(events[-1], AnswerDone)
    assert text_of(events) == "Twelve days [1] per year [3]."
    done = events[-1]
    assert done.status is MessageStatus.COMPLETE
    assert done.cited == (1,)
    assert done.invalid == (3,)
    assert done.usage == TokenUsage(100, 10)

    [result] = store.finished
    assert result.status is MessageStatus.COMPLETE
    assert result.content == "Twelve days [1] per year [3]."
    assert result.model_id == "scripted"
    assert result.cited == (1,)
    assert [s.ordinal for s in result.sources] == [1]
    assert result.trace is not None
    assert result.trace.query_rewritten is None
    assert result.trace.selected_chunk_ids == [result.sources[0].passage.chunk_id]


async def test_no_sources_refuses_without_calling_the_model() -> None:
    model = ScriptedModel(["should not run"])
    answers, store, _ = service(model, [])

    events = await events_of(answers, turn())

    assert model.calls == []
    assert text_of(events) == REFUSAL_TEXT
    done = events[-1]
    assert isinstance(done, AnswerDone)
    assert done.status is MessageStatus.REFUSED
    assert store.finished[0].status is MessageStatus.REFUSED
    assert store.finished[0].content == REFUSAL_TEXT
    assert store.finished[0].model_id is None


async def test_no_answer_marker_becomes_the_standard_refusal() -> None:
    answers, store, _ = service(ScriptedModel(["NO_", "ANSWER"]), [hit("Unrelated text.")])

    events = await events_of(answers, turn())

    assert text_of(events) == REFUSAL_TEXT
    assert "NO_ANSWER" not in text_of(events)
    assert events[-1].status is MessageStatus.REFUSED  # type: ignore[union-attr]
    assert store.finished[0].content == REFUSAL_TEXT
    assert store.finished[0].cited == ()


async def test_marker_after_some_text_still_refuses() -> None:
    answers, store, _ = service(ScriptedModel(["I cannot tell. ", "NO_ANSWER"]), [hit("x")])

    events = await events_of(answers, turn())

    assert events[-1].status is MessageStatus.REFUSED  # type: ignore[union-attr]
    assert store.finished[0].content == REFUSAL_TEXT


async def test_provider_failure_keeps_partial_text_and_reports_an_error() -> None:
    failure = ChatModelError("llm_unavailable", "The language model returned HTTP 529.")
    answers, store, _ = service(ScriptedModel(["Twelve "], fail=failure), [hit("Twelve days.")])

    events = await events_of(answers, turn())

    error = events[-1]
    assert isinstance(error, AnswerFailed)
    assert error.code == "llm_unavailable"
    assert not any(isinstance(e, AnswerDone) for e in events)
    [result] = store.finished
    assert result.status is MessageStatus.ERROR
    assert result.error_code == "llm_unavailable"
    assert result.content == "Twelve "
    assert len(result.sources) == 1


async def test_unexpected_errors_are_reported_without_details() -> None:
    answers, store, _ = service(ScriptedModel([], fail=RuntimeError("db password")), [hit("x")])

    events = await events_of(answers, turn())

    error = events[-1]
    assert isinstance(error, AnswerFailed)
    assert error.code == "internal_error"
    assert "password" not in error.detail
    assert store.finished[0].status is MessageStatus.ERROR


async def test_disconnect_while_the_model_writes_stores_the_answer_as_failed() -> None:
    class SlowModel(ScriptedModel):
        async def stream(
            self, *, system: str, messages: list[ChatMessage], max_tokens: int
        ) -> AsyncIterator[TextDelta | StreamEnd]:
            yield TextDelta("Twelve ")
            await asyncio.Event().wait()  # the model is still writing
            yield StreamEnd(TokenUsage(), None)

    answers, store, _ = service(SlowModel([]), [hit("Twelve days of leave.")])
    first_text = asyncio.Event()

    async def consume() -> None:
        async for event in answers.stream(turn()):
            if isinstance(event, AnswerText):
                first_text.set()

    task = asyncio.create_task(consume())
    await first_text.wait()
    await asyncio.sleep(0)  # the stream is now waiting for the model
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    [result] = store.finished
    assert result.status is MessageStatus.ERROR
    assert result.error_code == "client_disconnected"
    assert result.content == "Twelve "


async def test_closing_a_suspended_stream_stores_the_answer_as_failed() -> None:
    # What EventStreamResponse does when sending to a disconnected client fails.
    answers, store, _ = service(ScriptedModel(["Twelve ", "days."]), [hit("Twelve days.")])
    stream = answers.stream(turn())
    async for event in stream:
        if isinstance(event, AnswerText):
            break
    assert store.finished == []

    await stream.aclose()

    [result] = store.finished
    assert result.status is MessageStatus.ERROR
    assert result.error_code == "client_disconnected"


async def test_follow_up_questions_are_condensed_for_search() -> None:
    fast = ScriptedModel([], completion="How many days of leave for part-time staff?")
    model = ScriptedModel(["Ten days [1]."])
    answers, store, retriever = service(model, [hit("Part-time staff get ten days.")], fast=fast)
    history = [Turn("Who gets leave?", "All staff [1].")]

    events = await events_of(answers, turn(history))

    assert retriever.queries == ["How many days of leave for part-time staff?"]
    # The answer prompt still carries the original question and the history.
    [messages] = model.calls
    assert [m.role for m in messages] == ["user", "assistant", "user"]
    assert messages[-1].content.endswith("How many days of leave?")
    done = events[-1]
    assert isinstance(done, AnswerDone)
    assert done.usage == TokenUsage(120, 15)
    assert store.finished[0].trace is not None
    assert store.finished[0].trace.query_rewritten == "How many days of leave for part-time staff?"


async def test_unusable_condensation_falls_back_to_the_question() -> None:
    fast = ScriptedModel([], completion="   ")
    answers, _, retriever = service(ScriptedModel(["x [1]"]), [hit("x")], fast=fast)

    await events_of(answers, turn([Turn("q", "a")]))

    assert retriever.queries == ["How many days of leave?"]
