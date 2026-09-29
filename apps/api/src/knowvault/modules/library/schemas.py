"""Request and response bodies for the library API."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

CollectionName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]

DocumentKind = Literal["file", "note"]
DocumentStatus = Literal["pending", "processing", "ready", "failed"]


class CollectionCreate(BaseModel):
    name: CollectionName
    description: Description | None = None


class CollectionUpdate(BaseModel):
    name: CollectionName | None = None
    description: Description | None = None


class CollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    document_count: int
    created_at: datetime
    updated_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: DocumentKind
    title: str
    status: DocumentStatus
    mime_type: str
    original_filename: str | None
    size_bytes: int
    page_count: int | None
    collection_id: uuid.UUID | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    # Pass as `cursor` to fetch the next page; null when there are no more items.
    next_cursor: str | None


class DocumentUpdate(BaseModel):
    """Only the fields that are sent are changed. Send `collection_id: null` to unassign."""

    title: Title | None = None
    collection_id: uuid.UUID | None = None


class NoteCreate(BaseModel):
    title: Title
    body_md: Annotated[str, Field(min_length=1)]
    collection_id: uuid.UUID | None = None


class NoteUpdate(BaseModel):
    title: Title
    body_md: Annotated[str, Field(min_length=1)]


class NoteOut(DocumentOut):
    body_md: str
