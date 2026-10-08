"""Retrieval through the knowledge graph: the chunks that mention entities a query names.

Implements the retrieval module's `EntityLinks` port. Retrieval does not import the graph; the
application wires this in (`main.py`, the evaluation).
"""

import math
import uuid
from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, column, func, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.modules.graph.domain.model import EntityType, query_keys
from knowvault.modules.graph.infrastructure.models import (
    Entity,
    EntityAlias,
    EntityMention,
    Relation,
)
from knowvault.modules.retrieval.domain.model import SearchScope

GraphRetrieval = Literal["none", "entities", "neighbours"]

_documents = table(
    "documents", column("id"), column("owner_id"), column("collection_id"), column("status")
)
_READY = "ready"
# Mentions read per query at most; a name in every passage adds nothing to the ranking.
_MAX_MENTIONS = 5000


def _in_scope(scope: SearchScope) -> list[ColumnElement[bool]]:
    """Conditions on `documents` that keep the owner's ready documents in scope."""
    conditions = [_documents.c.owner_id == scope.owner_id, _documents.c.status == _READY]
    if scope.collection_id is not None:
        conditions.append(_documents.c.collection_id == scope.collection_id)
    if scope.document_ids:
        conditions.append(_documents.c.id.in_(scope.document_ids))
    return conditions


class PostgresEntityLinks:
    """Ranks chunks by the entities of the query they mention.

    Each entity named in the query (by its key or one of its aliases) adds its inverse
    document frequency to every chunk that mentions it, so a rare code outweighs a name found
    in every document. With `neighbours`, the entities most often mentioned together with
    them also count, at `neighbour_weight`.
    """

    def __init__(
        self,
        *,
        neighbours: bool = False,
        neighbours_per_entity: int = 5,
        neighbour_weight: float = 0.5,
    ) -> None:
        self._neighbours = neighbours
        self._neighbours_per_entity = neighbours_per_entity
        self._neighbour_weight = neighbour_weight

    async def chunks_for_query(
        self, session: AsyncSession, *, query: str, scope: SearchScope, limit: int
    ) -> list[uuid.UUID]:
        weights = await self._entities(session, query, scope.owner_id)
        if not weights:
            return []

        mentions = (
            await session.execute(
                select(EntityMention.entity_id, EntityMention.chunk_id, EntityMention.document_id)
                .join(_documents, _documents.c.id == EntityMention.document_id)
                .where(
                    EntityMention.owner_id == scope.owner_id,
                    EntityMention.entity_id.in_(list(weights)),
                    *_in_scope(scope),
                )
                .limit(_MAX_MENTIONS)
            )
        ).all()
        if not mentions:
            return []
        documents = await session.scalar(
            select(func.count()).select_from(_documents).where(*_in_scope(scope))
        )

        documents_of: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
        for entity_id, _, document_id in mentions:
            documents_of[entity_id].add(document_id)
        idf = {
            entity_id: math.log(1 + (documents or 1) / len(found))
            for entity_id, found in documents_of.items()
        }
        scores: dict[uuid.UUID, float] = defaultdict(float)
        for entity_id, chunk_id, _ in mentions:
            scores[chunk_id] += weights[entity_id] * idf[entity_id]
        ranked = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))
        return ranked[:limit]

    async def _entities(
        self, session: AsyncSession, query: str, owner_id: uuid.UUID
    ) -> dict[uuid.UUID, float]:
        """Weight of each entity that counts for the query: 1 if named, less if a neighbour."""
        keys = query_keys(query)

        def named(model: type[Entity] | type[EntityAlias]) -> Any:
            return or_(
                and_(model.type == EntityType.CODE.value, model.normalized_name.in_(keys.codes)),
                and_(model.type != EntityType.CODE.value, model.normalized_name.in_(keys.names)),
            )

        found = await session.scalars(
            select(Entity.id)
            .where(Entity.owner_id == owner_id, named(Entity))
            .union(
                select(EntityAlias.entity_id).where(
                    EntityAlias.owner_id == owner_id, named(EntityAlias)
                )
            )
        )
        weights = dict.fromkeys(found, 1.0)
        if not weights or not self._neighbours:
            return weights

        pairs = await session.execute(
            select(Relation.source_entity_id, Relation.target_entity_id, func.count())
            .where(
                Relation.owner_id == owner_id,
                or_(
                    Relation.source_entity_id.in_(list(weights)),
                    Relation.target_entity_id.in_(list(weights)),
                ),
            )
            .group_by(Relation.source_entity_id, Relation.target_entity_id)
        )
        related: dict[uuid.UUID, list[tuple[int, uuid.UUID]]] = defaultdict(list)
        for source, target, count in pairs:
            if source in weights and target not in weights:
                related[source].append((count, target))
            elif target in weights and source not in weights:
                related[target].append((count, source))
        for candidates in related.values():
            candidates.sort(key=lambda item: (-item[0], str(item[1])))
            for _, neighbour in candidates[: self._neighbours_per_entity]:
                weights[neighbour] = self._neighbour_weight
        return weights


def build_entity_links(mode: GraphRetrieval) -> PostgresEntityLinks | None:
    """The graph retrieval of a `GRAPH_RETRIEVAL` setting; None when it is off."""
    if mode == "none":
        return None
    return PostgresEntityLinks(neighbours=mode == "neighbours")
