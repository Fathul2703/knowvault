"""The graph in PostgreSQL: writes for extraction, reads for the API. Scoped by owner."""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import column, delete, distinct, exists, func, or_, select, table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core import jobs
from knowvault.modules.graph.application.extraction import EXTRACT_GRAPH_JOB
from knowvault.modules.graph.application.ports import DocumentChunks, GraphCounts, Resolution
from knowvault.modules.graph.domain.model import ChunkGraph, ChunkText, EntityType, may_merge
from knowvault.modules.graph.infrastructure.models import (
    Entity,
    EntityAlias,
    EntityMention,
    Relation,
)

# Only the columns the graph reads; it does not depend on the library or ingestion modules.
_documents = table(
    "documents",
    column("id"),
    column("owner_id"),
    column("collection_id"),
    column("title"),
    column("status"),
    column("content_version"),
)
_chunks = table("chunks", column("id"), column("document_id"), column("ordinal"), column("content"))
_READY = "ready"
_SNIPPET_CHARS = 90


class PostgresGraphStore:
    # --- Extraction ------------------------------------------------------------------------

    async def load_document(
        self, session: AsyncSession, document_id: uuid.UUID, content_version: int
    ) -> DocumentChunks | None:
        owner_id = await session.scalar(
            select(_documents.c.owner_id).where(
                _documents.c.id == document_id,
                _documents.c.content_version == content_version,
                _documents.c.status == _READY,
            )
        )
        if owner_id is None:
            return None
        rows = await session.execute(
            select(_chunks.c.id, _chunks.c.content)
            .where(_chunks.c.document_id == document_id)
            .order_by(_chunks.c.ordinal)
        )
        return DocumentChunks(
            document_id, owner_id, content_version, [ChunkText(i, text) for i, text in rows]
        )

    async def lock_current(
        self, session: AsyncSession, document_id: uuid.UUID, content_version: int
    ) -> bool:
        current = await session.scalar(
            select(_documents.c.content_version)
            .where(_documents.c.id == document_id, _documents.c.status == _READY)
            .with_for_update()
        )
        return current == content_version

    async def _resolve(
        self,
        session: AsyncSession,
        owner: uuid.UUID,
        entity_type: str,
        key: str,
        name: str,
        vector: list[float] | None,
        resolution: Resolution | None,
    ) -> uuid.UUID:
        """The entity a found name refers to; created if none."""
        found = await session.scalar(
            select(Entity.id).where(
                Entity.owner_id == owner, Entity.type == entity_type, Entity.normalized_name == key
            )
        )
        if found is not None:
            return found
        found = await session.scalar(
            select(EntityAlias.entity_id).where(
                EntityAlias.owner_id == owner,
                EntityAlias.type == entity_type,
                EntityAlias.normalized_name == key,
            )
        )
        if found is not None:
            return found
        if vector is not None and resolution is not None:
            distance = Entity.embedding.cosine_distance(vector)
            candidates = await session.execute(
                select(Entity.id, Entity.name, (1 - distance).label("similarity"))
                .where(
                    Entity.owner_id == owner,
                    Entity.type == entity_type,
                    Entity.embedding_model == resolution.embedding_model,
                    Entity.embedding.is_not(None),
                )
                .order_by(distance)
                .limit(5)
            )
            for candidate_id, candidate_name, similarity in candidates:
                if may_merge(name, candidate_name, float(similarity), resolution.threshold):
                    await session.execute(
                        insert(EntityAlias)
                        .values(
                            owner_id=owner,
                            type=entity_type,
                            normalized_name=key,
                            entity_id=candidate_id,
                            name=name,
                            similarity=round(float(similarity), 4),
                        )
                        .on_conflict_do_nothing()
                    )
                    merged: uuid.UUID = candidate_id
                    return merged
        await session.execute(
            insert(Entity)
            .values(
                id=uuid.uuid4(),
                owner_id=owner,
                type=entity_type,
                normalized_name=key,
                name=name,
                embedding=vector,
                embedding_model=resolution.embedding_model
                if vector is not None and resolution
                else None,
            )
            .on_conflict_do_nothing(constraint="uq_entities_owner_key")
        )
        # Inserted above, or by a concurrent extraction for the same owner.
        created = await session.execute(
            select(Entity.id).where(
                Entity.owner_id == owner, Entity.type == entity_type, Entity.normalized_name == key
            )
        )
        return created.scalar_one()

    async def replace_document_graph(
        self,
        session: AsyncSession,
        document: DocumentChunks,
        graphs: list[ChunkGraph],
        resolution: Resolution | None = None,
    ) -> GraphCounts:
        owner = document.owner_id
        await session.execute(
            delete(EntityMention).where(EntityMention.document_id == document.document_id)
        )
        await session.execute(delete(Relation).where(Relation.document_id == document.document_id))

        # Entities: one per (type, key) per owner, created on first mention unless the name is
        # another way of writing an existing entity (ADR 0016).
        names: dict[tuple[str, str], str] = {}
        for graph in graphs:
            for entity in graph.entities:
                names.setdefault((entity.type.value, entity.key[:200]), entity.name[:200])
        ids: dict[tuple[str, str], uuid.UUID] = {}
        for (entity_type, key), name in names.items():
            ids[(entity_type, key)] = await self._resolve(
                session,
                owner,
                entity_type,
                key,
                name,
                resolution.vectors.get((entity_type, key)) if resolution else None,
                resolution,
            )

        def entity_id(entity_type: EntityType, key: str) -> uuid.UUID:
            return ids[(entity_type.value, key[:200])]

        mentions: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
        relations: set[tuple[uuid.UUID, uuid.UUID, str, uuid.UUID]] = set()
        for graph in graphs:
            for entity in graph.entities:
                mentions[(entity_id(entity.type, entity.key), graph.chunk_id)] += entity.count
            for relation in graph.relations:
                source = entity_id(relation.source.type, relation.source.key)
                target = entity_id(relation.target.type, relation.target.key)
                if source != target:
                    relations.add((source, target, relation.type, graph.chunk_id))
        if mentions:
            await session.execute(
                insert(EntityMention).values(
                    [
                        {
                            "entity_id": entity,
                            "chunk_id": chunk,
                            "document_id": document.document_id,
                            "owner_id": owner,
                            "count": count,
                        }
                        for (entity, chunk), count in mentions.items()
                    ]
                )
            )
        if relations:
            await session.execute(
                insert(Relation).values(
                    [
                        {
                            "source_entity_id": source,
                            "target_entity_id": target,
                            "type": relation_type,
                            "chunk_id": chunk,
                            "document_id": document.document_id,
                            "owner_id": owner,
                        }
                        for source, target, relation_type, chunk in relations
                    ]
                )
            )

        # Entities no document mentions any more (e.g. after an edit) disappear.
        await session.execute(
            delete(Entity).where(
                Entity.owner_id == owner,
                ~exists().where(EntityMention.entity_id == Entity.id),
            )
        )
        return GraphCounts(len(set(ids.values())), len(mentions), len(relations))

    # --- Reads -----------------------------------------------------------------------------

    async def overview(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None,
        document_id: uuid.UUID | None,
        limit: int,
    ) -> "GraphView":
        """The most mentioned entities in scope and the relations among them."""
        scope = [EntityMention.owner_id == owner_id]
        if document_id is not None:
            scope.append(EntityMention.document_id == document_id)
        if collection_id is not None:
            scope.append(
                EntityMention.document_id.in_(
                    select(_documents.c.id).where(
                        _documents.c.owner_id == owner_id,
                        _documents.c.collection_id == collection_id,
                    )
                )
            )
        counts = (
            select(
                EntityMention.entity_id.label("entity_id"),
                func.sum(EntityMention.count).label("mentions"),
                func.count(distinct(EntityMention.document_id)).label("documents"),
            )
            .where(*scope)
            .group_by(EntityMention.entity_id)
            .subquery()
        )
        rows = await session.execute(
            select(Entity.id, Entity.name, Entity.type, counts.c.mentions, counts.c.documents)
            .join(counts, counts.c.entity_id == Entity.id)
            .order_by(counts.c.mentions.desc(), Entity.name)
            .limit(limit)
        )
        nodes = [
            NodeView(entity_id, name, entity_type, int(mentions), int(documents))
            for entity_id, name, entity_type, mentions, documents in rows
        ]
        node_ids = [node.id for node in nodes]
        edges: list[EdgeView] = []
        if node_ids:
            edge_scope = [
                Relation.owner_id == owner_id,
                Relation.source_entity_id.in_(node_ids),
                Relation.target_entity_id.in_(node_ids),
            ]
            if document_id is not None:
                edge_scope.append(Relation.document_id == document_id)
            if collection_id is not None:
                edge_scope.append(
                    Relation.document_id.in_(
                        select(_documents.c.id).where(
                            _documents.c.owner_id == owner_id,
                            _documents.c.collection_id == collection_id,
                        )
                    )
                )
            edge_rows = await session.execute(
                select(
                    Relation.source_entity_id,
                    Relation.target_entity_id,
                    Relation.type,
                    func.count().label("weight"),
                )
                .where(*edge_scope)
                .group_by(Relation.source_entity_id, Relation.target_entity_id, Relation.type)
            )
            edges = [EdgeView(s, t, kind, int(w)) for s, t, kind, w in edge_rows]
        return GraphView(nodes, edges)

    async def entity(
        self, session: AsyncSession, owner_id: uuid.UUID, entity_id: uuid.UUID
    ) -> "EntityView | None":
        entity = await session.scalar(
            select(Entity).where(Entity.id == entity_id, Entity.owner_id == owner_id)
        )
        if entity is None:
            return None
        mention_rows = await session.execute(
            select(
                EntityMention.document_id,
                _documents.c.title,
                _chunks.c.ordinal,
                _chunks.c.content,
                EntityMention.count,
            )
            .join(_chunks, _chunks.c.id == EntityMention.chunk_id)
            .join(_documents, _documents.c.id == EntityMention.document_id)
            .where(EntityMention.entity_id == entity_id, EntityMention.owner_id == owner_id)
            .order_by(_documents.c.title, _chunks.c.ordinal)
            .limit(50)
        )
        mentions = [
            MentionView(document, title, ordinal, snippet(content, entity.name), count)
            for document, title, ordinal, content, count in mention_rows
        ]
        other = func.coalesce(
            func.nullif(Relation.source_entity_id, entity_id), Relation.target_entity_id
        ).label("other")
        neighbour_rows = await session.execute(
            select(Entity.id, Entity.name, Entity.type, func.count().label("weight"))
            .select_from(Relation)
            .join(Entity, Entity.id == other)
            .where(
                Relation.owner_id == owner_id,
                or_(Relation.source_entity_id == entity_id, Relation.target_entity_id == entity_id),
            )
            .group_by(Entity.id, Entity.name, Entity.type)
            .order_by(func.count().desc(), Entity.name)
            .limit(20)
        )
        neighbours = [
            NeighbourView(n_id, name, n_type, int(weight))
            for n_id, name, n_type, weight in neighbour_rows
        ]
        alias_rows = await session.execute(
            select(EntityAlias.name, EntityAlias.similarity)
            .where(EntityAlias.entity_id == entity_id, EntityAlias.owner_id == owner_id)
            .order_by(EntityAlias.similarity.desc(), EntityAlias.name)
        )
        aliases = [AliasView(name, float(similarity)) for name, similarity in alias_rows]
        return EntityView(entity.id, entity.name, entity.type, mentions, neighbours, aliases)


def snippet(content: str, name: str) -> str:
    """Text around the first mention of `name`, or the start of the chunk."""
    flat = " ".join(content.split())
    at = flat.casefold().find(name.casefold())
    if at < 0:
        return flat[: 2 * _SNIPPET_CHARS] + ("…" if len(flat) > 2 * _SNIPPET_CHARS else "")
    start = max(0, at - _SNIPPET_CHARS)
    end = min(len(flat), at + len(name) + _SNIPPET_CHARS)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


@dataclass(frozen=True)
class NodeView:
    id: uuid.UUID
    name: str
    type: str
    mentions: int
    documents: int


@dataclass(frozen=True)
class EdgeView:
    source: uuid.UUID
    target: uuid.UUID
    type: str
    weight: int


@dataclass(frozen=True)
class GraphView:
    nodes: list[NodeView]
    edges: list[EdgeView]


@dataclass(frozen=True)
class MentionView:
    document_id: uuid.UUID
    document_title: str
    chunk_ordinal: int
    snippet: str
    count: int


@dataclass(frozen=True)
class NeighbourView:
    id: uuid.UUID
    name: str
    type: str
    weight: int


@dataclass(frozen=True)
class AliasView:
    name: str
    similarity: float


@dataclass(frozen=True)
class EntityView:
    id: uuid.UUID
    name: str
    type: str
    mentions: list[MentionView]
    neighbours: list[NeighbourView]
    aliases: list[AliasView]


async def queue_extraction(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    content_version: int,
    max_attempts: int,
) -> None:
    """Queues graph extraction for a document version, inside the caller's transaction."""
    await jobs.enqueue(
        session,
        type=EXTRACT_GRAPH_JOB,
        resource_id=document_id,
        payload={"content_version": content_version},
        max_attempts=max_attempts,
    )


async def queue_all_ready(session: AsyncSession, *, max_attempts: int) -> int:
    """Queues extraction for every ready document (backfill after enabling the graph)."""
    rows = list(
        await session.execute(
            select(_documents.c.id, _documents.c.content_version).where(
                _documents.c.status == _READY
            )
        )
    )
    for document_id, version in rows:
        await queue_extraction(
            session, document_id=document_id, content_version=version, max_attempts=max_attempts
        )
    return len(rows)
