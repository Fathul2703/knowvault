"""HTTP endpoint for semantic search."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from knowvault.core.db import SessionDep
from knowvault.core.deps import EmbeddingsDep
from knowvault.core.errors import Problem
from knowvault.modules.identity.dependencies import CurrentUser
from knowvault.modules.retrieval.application.search import SearchService
from knowvault.modules.retrieval.domain.model import MAX_TOP_K, SearchScope
from knowvault.modules.retrieval.infrastructure.pgvector_index import PgVectorIndex

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


class SearchRequest(BaseModel):
    """The searching user always comes from the session, never from the request body."""

    # Unknown fields (for example a `user_id`) are rejected rather than silently ignored.
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=MAX_TOP_K)] = 8
    collection_id: uuid.UUID | None = None
    document_ids: Annotated[list[uuid.UUID], Field(max_length=100)] = []


class SearchResultOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_kind: str
    ordinal: int
    content: str
    page_start: int | None
    page_end: int | None
    heading_path: list[str]
    score: float


class SearchResponse(BaseModel):
    query: str
    embedding_model: str
    results: list[SearchResultOut]


def get_search_service(embeddings: EmbeddingsDep) -> SearchService:
    return SearchService(embeddings, PgVectorIndex())


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        code: {"model": Problem, "content": {"application/problem+json": {}}}
        for code in (401, 403, 415, 422)
    },
)
async def search(
    body: SearchRequest,
    user: CurrentUser,
    session: SessionDep,
    service: Annotated[SearchService, Depends(get_search_service)],
) -> SearchResponse:
    """Returns the chunks of the user's ready documents most similar to the query.

    Results are ordered by cosine similarity and carry what a citation needs: document,
    chunk position, page range (PDF) or heading trail.
    """
    result = await service.search(
        session,
        query=body.query,
        scope=SearchScope(
            owner_id=user.id,
            collection_id=body.collection_id,
            document_ids=tuple(body.document_ids),
        ),
        top_k=body.top_k,
    )
    return SearchResponse(
        query=body.query,
        embedding_model=result.embedding_model,
        results=[
            SearchResultOut(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_title=hit.document_title,
                document_kind=hit.document_kind,
                ordinal=hit.ordinal,
                content=hit.content,
                page_start=hit.page_start,
                page_end=hit.page_end,
                heading_path=list(hit.heading_path),
                score=round(hit.score, 4),
            )
            for hit in result.hits
        ],
    )
