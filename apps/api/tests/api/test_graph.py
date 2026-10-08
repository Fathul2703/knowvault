"""The knowledge graph end to end: extraction jobs, graph and entity endpoints."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.modules.graph.application.extraction import GraphExtraction
from knowvault.modules.graph.domain.heuristic import HeuristicExtractor
from knowvault.modules.graph.infrastructure.models import Entity
from knowvault.modules.graph.infrastructure.store import PostgresGraphStore
from knowvault.worker import build_pipeline, run_once
from tests.conftest import RegisterFn

GRAPH = "/api/v1/graph"
MakeInvite = Callable[[], Awaitable[str]]

BILLING = (
    "# Billing errors\n\nERR_4713 means the card was declined by the Issuing Bank. "
    "The Billing Service retries after 24 hours; ERR_4713 then emails the customer."
)
WAREHOUSE = "# Gudang\n\nGudang baru di Bekasi melayani pelanggan di Jabodetabek."


@pytest.fixture
def run_worker(settings: Settings, database: Database) -> Callable[[], Awaitable[None]]:
    pipeline = build_pipeline(settings, database)

    async def _run() -> None:
        while await run_once(database, pipeline, settings):
            pass

    return _run


async def note(client: AsyncClient, title: str, body: str, **extra: object) -> str:
    response = await client.post("/api/v1/notes", json={"title": title, "body_md": body, **extra})
    assert response.status_code == 201, response.text
    document_id: str = response.json()["id"]
    return document_id


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register(email="ada@example.com")
    return client


def by_name(graph: dict[str, list[dict[str, object]]]) -> dict[str, dict[str, object]]:
    return {str(node["name"]): node for node in graph["nodes"]}


async def test_graph_is_built_after_processing(
    ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]
) -> None:
    billing = await note(ada, "Billing", BILLING)
    await note(ada, "Warehouse", WAREHOUSE)
    await run_worker()

    graph = (await ada.get(GRAPH)).json()
    nodes = by_name(graph)
    assert nodes["ERR_4713"]["type"] == "code"
    assert nodes["ERR_4713"]["mentions"] == 2
    assert {"Issuing Bank", "Billing Service", "Bekasi", "Jabodetabek"} <= set(nodes)
    # Entities of the same passage are related; those of different documents are not.
    pairs = {frozenset((edge["source"], edge["target"])) for edge in graph["edges"]}
    assert frozenset((nodes["ERR_4713"]["id"], nodes["Issuing Bank"]["id"])) in pairs
    assert frozenset((nodes["ERR_4713"]["id"], nodes["Bekasi"]["id"])) not in pairs

    detail = (await ada.get(f"{GRAPH}/entities/{nodes['ERR_4713']['id']}")).json()
    assert detail["name"] == "ERR_4713"
    [mention] = detail["mentions"]
    assert mention["document_id"] == billing
    assert mention["chunk_ordinal"] == 0
    assert "ERR_4713 means the card was declined" in mention["snippet"]
    assert {n["name"] for n in detail["neighbours"]} >= {"Issuing Bank", "Billing Service"}

    scoped = by_name((await ada.get(GRAPH, params={"document_id": billing})).json())
    assert "Bekasi" not in scoped
    assert "ERR_4713" in scoped


async def test_editing_a_note_replaces_its_graph(
    ada: AsyncClient, run_worker: Callable[[], Awaitable[None]], database: Database
) -> None:
    billing = await note(ada, "Billing", BILLING)
    await run_worker()
    response = await ada.put(
        f"/api/v1/notes/{billing}",
        json={"title": "Billing", "body_md": "ERR_9001 means the invoice is locked."},
    )
    assert response.status_code == 200
    await run_worker()

    nodes = by_name((await ada.get(GRAPH)).json())
    assert set(nodes) == {"ERR_9001"}
    async with database.sessionmaker() as session:
        # Entities no longer mentioned anywhere are removed.
        assert await session.scalar(select(func.count()).select_from(Entity)) == 1


async def test_deleted_documents_leave_the_graph(
    ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]
) -> None:
    billing = await note(ada, "Billing", BILLING)
    await note(ada, "Warehouse", WAREHOUSE)
    await run_worker()
    entity_id = by_name((await ada.get(GRAPH)).json())["ERR_4713"]["id"]

    assert (await ada.delete(f"/api/v1/documents/{billing}")).status_code == 204

    nodes = by_name((await ada.get(GRAPH)).json())
    assert "ERR_4713" not in nodes
    assert "Bekasi" in nodes
    detail = (await ada.get(f"{GRAPH}/entities/{entity_id}")).json()
    assert detail["mentions"] == []
    assert detail["neighbours"] == []


async def test_collection_scope(
    ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]
) -> None:
    hr = (await ada.post("/api/v1/collections", json={"name": "Ops"})).json()["id"]
    await note(ada, "Warehouse", WAREHOUSE, collection_id=hr)
    await note(ada, "Billing", BILLING)
    await run_worker()

    nodes = by_name((await ada.get(GRAPH, params={"collection_id": hr})).json())
    assert "Bekasi" in nodes
    assert "ERR_4713" not in nodes


async def test_graphs_are_private(
    ada: AsyncClient,
    run_worker: Callable[[], Awaitable[None]],
    app_client_factory: Callable[[], AsyncClient],
    make_invite: MakeInvite,
) -> None:
    await note(ada, "Billing", BILLING)
    await run_worker()
    entity_id = by_name((await ada.get(GRAPH)).json())["ERR_4713"]["id"]

    async with app_client_factory() as eve:
        await eve.post(
            "/api/v1/auth/register",
            json={
                "invite_code": await make_invite(),
                "email": "eve@example.com",
                "password": "correct horse battery",
                "display_name": "Eve",
            },
        )
        await note(eve, "Eve's billing", "ERR_4713 is also in my notes.")
        await run_worker()
        eve_nodes = by_name((await eve.get(GRAPH)).json())
        # Same code, separate entity, own counts.
        assert eve_nodes["ERR_4713"]["id"] != entity_id
        assert eve_nodes["ERR_4713"]["mentions"] == 1
        assert (await eve.get(f"{GRAPH}/entities/{entity_id}")).status_code == 404
    assert (await ada.get(GRAPH)).json()["nodes"][0]["mentions"] == 2


async def test_no_graph_when_disabled(
    ada: AsyncClient, settings: Settings, database: Database
) -> None:
    disabled = settings.model_copy(update={"graph_extractor": "none"})
    pipeline = build_pipeline(disabled, database)
    await note(ada, "Billing", BILLING)
    while await run_once(database, pipeline, disabled):
        pass
    assert (await ada.get(GRAPH)).json() == {"nodes": [], "edges": []}


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(GRAPH)).status_code == 401


class GroupEmbeddings:
    """Names of the same group get the same vector; everything else is unrelated."""

    def __init__(self, groups: list[set[str]]) -> None:
        self._groups = groups

    @property
    def model_id(self) -> str:
        return "groups"

    @property
    def dimensions(self) -> int:
        return 1024

    def _vector(self, text: str) -> list[float]:
        index = next((i for i, g in enumerate(self._groups) if text in g), None)
        vector = [0.0] * 1024
        vector[index if index is not None else 1023 - (hash(text) % 500)] = 1.0
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture
def run_resolving_worker(
    settings: Settings, database: Database
) -> Callable[[list[set[str]]], Awaitable[None]]:
    async def _run(groups: list[set[str]]) -> None:
        pipeline = build_pipeline(settings, database)
        graph = GraphExtraction(
            database.sessionmaker,
            PostgresGraphStore(),
            HeuristicExtractor(),
            embeddings=GroupEmbeddings(groups),
            merge_threshold=0.82,
        )
        while await run_once(database, pipeline, settings, graph):
            pass

    return _run


async def test_other_ways_of_writing_a_name_join_its_entity(
    ada: AsyncClient, run_resolving_worker: Callable[[list[set[str]]], Awaitable[None]]
) -> None:
    await note(ada, "Report", "Our office in the Netherlands opened in March.")
    await run_resolving_worker([{"Netherlands", "Belanda"}])
    await note(ada, "Laporan", "Kantor kami di Belanda dibuka bulan Maret.")
    await note(ada, "Calendar", "The office counts Business Days. Each Business Day starts at 9.")
    await run_resolving_worker([{"Netherlands", "Belanda"}])

    nodes = by_name((await ada.get(GRAPH)).json())
    # The first spelling names the entity; the other became an alias.
    assert "Belanda" not in nodes
    assert nodes["Netherlands"]["documents"] == 2
    detail = (await ada.get(f"{GRAPH}/entities/{nodes['Netherlands']['id']}")).json()
    assert detail["aliases"] == [{"name": "Belanda", "similarity": 1.0}]
    # Plurals share a key without any similarity.
    business = [name for name in nodes if name.startswith("Business Day")]
    assert len(business) == 1


async def test_names_containing_each_other_stay_apart(
    ada: AsyncClient, run_resolving_worker: Callable[[list[set[str]]], Awaitable[None]]
) -> None:
    await note(ada, "Contract", "The Customer owns all Customer Data stored in the Platform.")
    await run_resolving_worker([{"Customer", "Customer Data"}])

    nodes = by_name((await ada.get(GRAPH)).json())
    assert {"Customer", "Customer Data"} <= set(nodes)


async def test_codes_are_never_merged_by_similarity(
    ada: AsyncClient, run_resolving_worker: Callable[[list[set[str]]], Awaitable[None]]
) -> None:
    await note(ada, "Errors", "ERR_4711 is a timeout. ERR_4712 is a full quota.")
    await run_resolving_worker([{"ERR_4711", "ERR_4712"}])

    nodes = by_name((await ada.get(GRAPH)).json())
    assert {"ERR_4711", "ERR_4712"} <= set(nodes)
