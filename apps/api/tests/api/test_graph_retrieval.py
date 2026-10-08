"""Graph retrieval (ADR 0018): chunks found through the entities a query names."""

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import text

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.core.storage import ObjectStorage
from knowvault.main import create_app
from knowvault.modules.graph.infrastructure.entity_links import (
    PostgresEntityLinks,
    build_entity_links,
)
from knowvault.modules.retrieval.domain.model import SearchScope
from tests.api.test_graph import ada, note, run_resolving_worker, run_worker  # noqa: F401

DECLINED = "ERR_4713 means the card was declined by the Issuing Bank."
RETRIED = "The Billing Service retries ERR_4713 after 24 hours."
WAREHOUSE = "Gudang baru di Bekasi melayani pelanggan di Jabodetabek."


async def owner(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])


async def chunk_documents(
    database: Database, links: PostgresEntityLinks, query: str, scope: SearchScope
) -> list[str]:
    """Titles of the documents of the chunks found, in order."""
    async with database.sessionmaker() as session:
        chunk_ids = await links.chunks_for_query(session, query=query, scope=scope, limit=10)
        titles = []
        for chunk_id in chunk_ids:
            title = await session.scalar(
                text(
                    "SELECT d.title FROM chunks c JOIN documents d ON d.id = c.document_id "
                    "WHERE c.id = :id"
                ),
                {"id": chunk_id},
            )
            titles.append(str(title))
    return titles


async def test_finds_the_chunks_of_entities_named_in_the_query(
    ada: AsyncClient,  # noqa: F811
    run_worker: Callable[[], Awaitable[None]],  # noqa: F811
    database: Database,
) -> None:
    await note(ada, "Declined", DECLINED)
    await note(ada, "Retried", RETRIED)
    await note(ada, "Warehouse", WAREHOUSE)
    await run_worker()
    scope = SearchScope(owner_id=await owner(ada))
    links = PostgresEntityLinks()

    # Lower case and a question mark do not hide the code.
    found = await chunk_documents(database, links, "what does err_4713 mean?", scope)
    assert sorted(found) == ["Declined", "Retried"]
    # A name in fewer documents weighs more: both entities beat one.
    found = await chunk_documents(database, links, "ERR_4713 and the issuing bank", scope)
    assert found[0] == "Declined"
    # No known entity, no chunks: the hybrid fusion is unchanged.
    assert await chunk_documents(database, links, "how are refunds handled", scope) == []


async def test_neighbours_extend_the_search_to_related_entities(
    ada: AsyncClient,  # noqa: F811
    run_worker: Callable[[], Awaitable[None]],  # noqa: F811
    database: Database,
) -> None:
    await note(ada, "Declined", DECLINED)
    await note(ada, "Retried", RETRIED)
    await run_worker()
    scope = SearchScope(owner_id=await owner(ada))

    direct = await chunk_documents(database, PostgresEntityLinks(), "Issuing Bank", scope)
    assert direct == ["Declined"]
    # ERR_4713 is mentioned with the Issuing Bank, so its other passage follows.
    expanded = await chunk_documents(
        database, PostgresEntityLinks(neighbours=True), "Issuing Bank", scope
    )
    assert expanded == ["Declined", "Retried"]


async def test_aliases_name_their_entity(
    ada: AsyncClient,  # noqa: F811
    run_resolving_worker: Callable[[list[set[str]]], Awaitable[None]],  # noqa: F811
    database: Database,
) -> None:
    await note(ada, "Report", "Our office in the Netherlands opened in March.")
    await run_resolving_worker([{"Netherlands", "Belanda"}])
    await note(ada, "Laporan", "Kantor kami di Belanda dibuka bulan Maret.")
    await run_resolving_worker([{"Netherlands", "Belanda"}])
    scope = SearchScope(owner_id=await owner(ada))

    found = await chunk_documents(database, PostgresEntityLinks(), "kantor di Belanda", scope)
    assert sorted(found) == ["Laporan", "Report"]


async def test_respects_the_search_scope(
    ada: AsyncClient,  # noqa: F811
    run_worker: Callable[[], Awaitable[None]],  # noqa: F811
    database: Database,
) -> None:
    ops = uuid.UUID((await ada.post("/api/v1/collections", json={"name": "Ops"})).json()["id"])
    await note(ada, "Declined", DECLINED, collection_id=str(ops))
    await note(ada, "Retried", RETRIED)
    await run_worker()
    me = await owner(ada)
    links = PostgresEntityLinks()

    assert await chunk_documents(
        database, links, "ERR_4713", SearchScope(owner_id=me, collection_id=ops)
    ) == ["Declined"]
    # Another user's graph is never searched.
    assert await chunk_documents(database, links, "ERR_4713", SearchScope(uuid.uuid4())) == []


def test_the_setting_wires_graph_retrieval(
    settings: Settings, database: Database, storage: ObjectStorage
) -> None:
    assert build_entity_links("none") is None
    off = create_app(settings, database, storage)
    assert off.state.entity_links is None
    on = create_app(settings.model_copy(update={"graph_retrieval": "entities"}), database, storage)
    assert isinstance(on.state.entity_links, PostgresEntityLinks)
