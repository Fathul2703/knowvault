"""Request and response bodies of the conversation endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from knowvault.modules.assistant.domain.model import MessageStatus

MAX_QUESTION_CHARS = 2000

Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class ConversationScope(BaseModel):
    """Documents answers may use. Empty means all of the user's ready documents."""

    model_config = ConfigDict(extra="forbid")

    collection_id: uuid.UUID | None = None
    document_ids: Annotated[list[uuid.UUID], Field(max_length=100)] = []


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title = Field(default="", description="Taken from the first question when empty.")
    scope: ConversationScope = ConversationScope()


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    scope: ConversationScope
    created_at: datetime
    updated_at: datetime


class ConversationPage(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None


class CitationOut(BaseModel):
    ordinal: int = Field(description="The n of [n] in the answer.")
    cited: bool = Field(description="Whether the answer cites this source.")
    chunk_id: uuid.UUID | None = Field(
        description="Null when the document was changed or deleted after the answer."
    )
    chunk_ordinal: int | None = Field(
        description="Position of the chunk in its document (the n of #chunk-n on the document "
        "page); null when the chunk no longer exists."
    )
    document_id: uuid.UUID | None = Field(description="Null when the document was deleted.")
    document_title: str
    quoted_text: str = Field(description="The source text as it was when the answer was written.")
    page_start: int | None
    page_end: int | None
    heading_path: list[str]


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    status: MessageStatus
    model_id: str | None
    error_code: str | None
    created_at: datetime
    citations: list[CitationOut]


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS),
    ]
