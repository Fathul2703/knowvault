"""Port for chat (text generation) models. Implementations live in `knowvault.adapters.chat`."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class TextDelta:
    """A piece of generated text."""

    text: str


@dataclass(frozen=True)
class StreamEnd:
    """Always the last event of a stream that did not fail."""

    usage: TokenUsage
    # Provider stop reason, e.g. "end_turn" or "max_tokens".
    stop_reason: str | None


@dataclass(frozen=True)
class Completion:
    text: str
    usage: TokenUsage


class ChatModelError(Exception):
    """The provider failed or could not be reached. Never contains prompt or document text."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class ChatModel(Protocol):
    @property
    def model_id(self) -> str:
        """Identifies the provider model; stored with every generated message."""
        ...

    def stream(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[TextDelta | StreamEnd]:
        """Generates a reply token by token. Raises ChatModelError on provider failures.

        Retries, if any, happen only before the first event: once text has been yielded a
        failure is raised to the caller.
        """
        ...

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> Completion:
        """Generates a whole reply. Raises ChatModelError on provider failures."""
        ...


@dataclass(frozen=True)
class ChatModels:
    """The two routes of docs/ARCHITECTURE.md §10.3: answers and cheap auxiliary calls."""

    # Writes answers from sources.
    answer: ChatModel
    # Cheaper model for query condensation.
    fast: ChatModel
