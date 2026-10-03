"""What the answer service needs from storage and search."""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from knowvault.core.chat import TokenUsage
from knowvault.modules.assistant.domain.model import MessageStatus, Source, Turn
from knowvault.modules.retrieval.domain.model import SearchHit, SearchScope


@dataclass(frozen=True)
class TurnStart:
    """A question accepted for answering: both messages exist, the answer is `streaming`."""

    conversation_id: uuid.UUID
    owner_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    question: str
    scope: SearchScope
    history: list[Turn]


@dataclass(frozen=True)
class RetrievalTrace:
    """Why these sources: IDs, ranks and scores only, never document text."""

    query_original: str
    query_rewritten: str | None
    candidates: list[dict[str, object]]
    selected_chunk_ids: list[uuid.UUID]
    params: dict[str, object]


@dataclass(frozen=True)
class TurnResult:
    status: MessageStatus
    content: str
    model_id: str | None
    usage: TokenUsage
    latency_ms: int
    error_code: str | None = None
    sources: list[Source] = field(default_factory=list)
    cited: tuple[int, ...] = ()
    trace: RetrievalTrace | None = None


class ConversationStore(Protocol):
    async def start_turn(
        self, *, owner_id: uuid.UUID, conversation_id: uuid.UUID, question: str
    ) -> TurnStart:
        """Records the question and an empty answer.

        Raises NotFoundError for a conversation the owner does not have, AnswerInProgressError
        while another answer of the owner is streaming, and TokenQuotaExceededError when the
        owner's daily token budget is spent.
        """
        ...

    async def finish_turn(self, turn: TurnStart, result: TurnResult) -> None:
        """Stores the answer, its sources and trace, and counts the tokens used."""
        ...


class Retriever(Protocol):
    async def retrieve(self, query: str, *, scope: SearchScope, top_k: int) -> list[SearchHit]:
        """Hybrid search; holds a database connection only while querying."""
        ...
