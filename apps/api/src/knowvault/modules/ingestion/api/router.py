"""HTTP endpoints for inspecting ingestion results."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from knowvault.core.db import SessionDep
from knowvault.core.errors import Problem
from knowvault.modules.identity.dependencies import CurrentUser
from knowvault.modules.ingestion.infrastructure.chunks import list_chunks
from knowvault.modules.library.processing import ensure_owned

router = APIRouter(prefix="/api/v1", tags=["documents"])


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordinal: int
    content: str
    char_count: int
    page_start: int | None
    page_end: int | None
    heading_path: list[str]


class ChunkPage(BaseModel):
    items: list[ChunkOut]
    total: int


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ChunkPage,
    responses={
        code: {"model": Problem, "content": {"application/problem+json": {}}}
        for code in (401, 404, 422)
    },
)
async def get_document_chunks(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ChunkPage:
    """The text chunks extracted from the document, in reading order."""
    await ensure_owned(session, user.id, document_id)
    chunks, total = await list_chunks(session, document_id, offset=offset, limit=limit)
    return ChunkPage(items=[ChunkOut.model_validate(c) for c in chunks], total=total)
