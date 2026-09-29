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
from knowvault.modules.retrieval.domain.model import MAX_TOP_K, SearchMode, SearchScope
from knowvault.modules.retrieval.infrastructure.postgres_index import PostgresChunkIndex

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


class SearchRequest(BaseModel):
    """The searching user always comes from the session, never from the request body."""

    # Unknown fields (for example a `user_id`) are rejected rather than silently ignored.
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    top_k: Annotated[int, Field(ge=1, le=MAX_TOP_K)] = 8
    collection_id: uuid.UUID | None = None
    document_ids: Annotated[list[uuid.UUID], Field(max_length=100)] = []
    mode: SearchMode = Field(
        default=SearchMode.HYBRID,
        description="hybrid: vector + full text fused with RRF (default); vector or fulltext: "
        "a single method, for debugging and evaluation",
    )


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
    score: float = Field(
        description="Ordering score of the mode: RRF score (hybrid), cosine similarity "
        "(vector) or ts_rank_cd (fulltext). Only comparable within one response."
    )
    similarity: float | None = Field(
        description="Cosine similarity to the query; null in fulltext mode or when the "
        "chunk has no current embedding."
    )
    vector_rank: int | None = Field(description="Rank among vector candidates (1-based).")
    fulltext_rank: int | None = Field(description="Rank among full-text candidates (1-based).")


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    # Null in fulltext mode, where the query is not embedded.
    embedding_model: str | None
    results: list[SearchResultOut]


def get_search_service(embeddings: EmbeddingsDep) -> SearchService:
    return SearchService(embeddings, PostgresChunkIndex())


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
    """Returns the chunks of the user's ready documents most relevant to the query.

    By default, semantic (vector) and keyword (full-text) results are fused with Reciprocal
    Rank Fusion. Each result carries what a citation needs: document, chunk position, page
    range (PDF) or heading trail.
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
        mode=body.mode,
    )
    return SearchResponse(
        query=body.query,
        mode=result.mode,
        embedding_model=result.embedding_model,
        results=[
            SearchResultOut(
                chunk_id=hit.chunk.chunk_id,
                document_id=hit.chunk.document_id,
                document_title=hit.chunk.document_title,
                document_kind=hit.chunk.document_kind,
                ordinal=hit.chunk.ordinal,
                content=hit.chunk.content,
                page_start=hit.chunk.page_start,
                page_end=hit.chunk.page_end,
                heading_path=list(hit.chunk.heading_path),
                score=round(hit.score, 6),
                similarity=None if hit.similarity is None else round(hit.similarity, 6),
                vector_rank=hit.vector_rank,
                fulltext_rank=hit.fulltext_rank,
            )
            for hit in result.hits
        ],
    )
