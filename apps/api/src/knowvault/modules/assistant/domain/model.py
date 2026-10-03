"""Conversations, sources and the fixed texts of the answer protocol."""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

# The model replies with exactly this when its sources cannot answer the question.
NO_ANSWER = "NO_ANSWER"
# Shown and stored instead of an answer when the question is refused.
REFUSAL_TEXT = "I couldn't find enough information in your documents to answer that."


class MessageStatus(StrEnum):
    STREAMING = "streaming"  # the answer is being written
    COMPLETE = "complete"
    REFUSED = "refused"  # not enough evidence in the user's documents
    ERROR = "error"  # the provider failed or the client went away


@dataclass(frozen=True)
class Passage:
    """A retrieved chunk, as much of it as an answer and its citation need."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    ordinal: int
    content: str
    page_start: int | None = None
    page_end: int | None = None
    heading_path: tuple[str, ...] = field(default_factory=tuple)

    @property
    def location(self) -> str | None:
        """Physical PDF pages, or the heading trail for other documents."""
        if self.page_start is not None:
            if self.page_end is None or self.page_end == self.page_start:
                return f"p. {self.page_start}"
            return f"pp. {self.page_start}\u2013{self.page_end}"
        if self.heading_path:
            return " > ".join(self.heading_path)
        return None


@dataclass(frozen=True)
class Source:
    """A passage given to the model, cited in the answer as `[ordinal]`."""

    ordinal: int
    passage: Passage


@dataclass(frozen=True)
class Turn:
    """An earlier question and its answer, sent as conversation history."""

    question: str
    answer: str
