"""HTTP endpoints for reading the knowledge graph."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from knowvault.core.db import SessionDep
from knowvault.core.errors import NotFoundError, Problem
from knowvault.modules.graph.infrastructure.store import PostgresGraphStore
from knowvault.modules.identity.dependencies import CurrentUser

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": Problem, "content": {"application/problem+json": {}}}
    for code in (401, 404, 422)
}


class GraphNode(BaseModel):
    id: uuid.UUID
    name: str
    type: str = Field(description="code, name, person, organization, place, product or concept")
    mentions: int = Field(description="Occurrences in the documents in scope.")
    documents: int = Field(description="Documents in scope that mention it.")


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    type: str = Field(description="co_occurs: mentioned in the same passage.")
    weight: int = Field(description="Passages that relate the two entities.")


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class EntityMentionOut(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_ordinal: int
    snippet: str
    count: int


class EntityNeighbourOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    weight: int


class EntityOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    mentions: list[EntityMentionOut]
    neighbours: list[EntityNeighbourOut]


@router.get("", response_model=GraphOut, responses=_ERRORS)
async def graph_overview(
    user: CurrentUser,
    session: SessionDep,
    collection_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> GraphOut:
    """The entities mentioned most often in the user's documents (optionally one collection or
    document) and the relations among them."""
    view = await PostgresGraphStore().overview(
        session, user.id, collection_id=collection_id, document_id=document_id, limit=limit
    )
    return GraphOut(
        nodes=[GraphNode(**node.__dict__) for node in view.nodes],
        edges=[GraphEdge(**edge.__dict__) for edge in view.edges],
    )


@router.get("/entities/{entity_id}", response_model=EntityOut, responses=_ERRORS)
async def get_entity(entity_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> EntityOut:
    """An entity with the passages that mention it and its most related entities."""
    view = await PostgresGraphStore().entity(session, user.id, entity_id)
    if view is None:
        raise NotFoundError("The entity does not exist.")
    return EntityOut(
        id=view.id,
        name=view.name,
        type=view.type,
        mentions=[EntityMentionOut(**m.__dict__) for m in view.mentions],
        neighbours=[EntityNeighbourOut(**n.__dict__) for n in view.neighbours],
    )
