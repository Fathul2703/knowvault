"""POST /api/v1/retrieval/search, end to end with the worker (fake embeddings)."""

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update

from knowvault.core import jobs
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.modules.ingestion.infrastructure.chunks import Chunk
from knowvault.modules.library.models import Document
from knowvault.modules.library.processing import queue_stale_embeddings
from knowvault.worker import build_pipeline, run_once
from tests.api.test_library import upload
from tests.conftest import RegisterFn
from tests.factories import make_pdf

SEARCH = "/api/v1/retrieval/search"
MakeInvite = Callable[[], Awaitable[str]]


@pytest.fixture
def run_worker(settings: Settings, database: Database) -> Callable[[], Awaitable[None]]:
    pipeline = build_pipeline(settings, database)

    async def _run() -> None:
        while await run_once(database, pipeline, settings):
            pass

    return _run


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register(email="ada@example.com")
    return client


@pytest.fixture
async def grace(
    app_client_factory: Callable[[], AsyncClient], make_invite: MakeInvite
) -> AsyncIterator[AsyncClient]:
    async with app_client_factory() as other:
        response = await other.post(
            "/api/v1/auth/register",
            json={
                "invite_code": await make_invite(),
                "email": "grace@example.com",
                "password": "another long password",
                "display_name": "Grace",
            },
        )
        assert response.status_code == 201
        yield other


async def note(client: AsyncClient, title: str, body: str, **extra: str) -> str:
    response = await client.post("/api/v1/notes", json={"title": title, "body_md": body, **extra})
    assert response.status_code == 201
    document_id: str = response.json()["id"]
    return document_id


@pytest.fixture
async def library(ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]) -> dict[str, str]:
    """Ada's processed documents: a PDF about vectors and two notes."""
    pdf = (
        await upload(
            ada,
            "vectors.pdf",
            make_pdf(
                [
                    "Introduction to the course.",
                    "Vector search finds passages by cosine similarity with pgvector.",
                ]
            ),
        )
    ).json()["id"]
    cooking = await note(
        ada, "Cooking", "# Recipes\n\nFried rice needs garlic and sweet soy sauce."
    )
    chunking = await note(ada, "Chunking", "# Retrieval\n\nChunks keep page numbers for citations.")
    await run_worker()
    return {"pdf": pdf, "cooking": cooking, "chunking": chunking}


class TestSearch:
    async def test_returns_relevant_chunks_with_citation_metadata(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        response = await ada.post(SEARCH, json={"query": "vector search cosine similarity"})
        assert response.status_code == 200
        body = response.json()
        assert body["embedding_model"] == "fake-bow"
        top = body["results"][0]
        assert top["document_id"] == library["pdf"]
        assert top["document_title"] == "vectors"
        assert top["document_kind"] == "file"
        assert "cosine similarity" in top["content"]
        assert (top["page_start"], top["page_end"]) == (1, 2)
        scores = [r["score"] for r in body["results"]]
        assert scores == sorted(scores, reverse=True)

    async def test_note_results_carry_their_heading_trail(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        body = (await ada.post(SEARCH, json={"query": "fried rice garlic"})).json()
        top = body["results"][0]
        assert top["document_id"] == library["cooking"]
        assert top["heading_path"] == ["Recipes"]
        assert top["page_start"] is None

    async def test_top_k_limits_results(self, ada: AsyncClient, library: dict[str, str]) -> None:
        body = (await ada.post(SEARCH, json={"query": "anything", "top_k": 2})).json()
        assert len(body["results"]) == 2
        everything = (await ada.post(SEARCH, json={"query": "anything"})).json()
        assert len(everything["results"]) == 3  # one chunk per document, fewer than top_k

    async def test_filters_by_collection_and_documents(
        self, ada: AsyncClient, library: dict[str, str], run_worker: Callable[[], Awaitable[None]]
    ) -> None:
        collection = (await ada.post("/api/v1/collections", json={"name": "Kitchen"})).json()
        await ada.patch(
            f"/api/v1/documents/{library['cooking']}", json={"collection_id": collection["id"]}
        )
        in_collection = (
            await ada.post(
                SEARCH, json={"query": "vector search", "collection_id": collection["id"]}
            )
        ).json()
        assert {r["document_id"] for r in in_collection["results"]} == {library["cooking"]}

        only = (
            await ada.post(
                SEARCH, json={"query": "vector search", "document_ids": [library["chunking"]]}
            )
        ).json()
        assert {r["document_id"] for r in only["results"]} == {library["chunking"]}

    async def test_documents_that_are_not_ready_are_excluded(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        await ada.put(
            f"/api/v1/notes/{library['chunking']}",
            json={"title": "Chunking", "body_md": "Rewritten, not processed yet."},
        )
        body = (await ada.post(SEARCH, json={"query": "citations page numbers"})).json()
        assert library["chunking"] not in {r["document_id"] for r in body["results"]}

    async def test_vectors_from_another_model_are_excluded(
        self, ada: AsyncClient, library: dict[str, str], database: Database
    ) -> None:
        async with database.sessionmaker() as session:
            await session.execute(
                update(Document)
                .where(Document.id == library["pdf"])
                .values(embedding_model="some-older-model")
            )
            await session.commit()
        body = (await ada.post(SEARCH, json={"query": "vector search cosine"})).json()
        assert library["pdf"] not in {r["document_id"] for r in body["results"]}

    async def test_empty_library_returns_no_results(self, ada: AsyncClient) -> None:
        body = (await ada.post(SEARCH, json={"query": "anything"})).json()
        assert body["results"] == []


class TestSearchSecurity:
    async def test_users_only_search_their_own_documents(
        self,
        ada: AsyncClient,
        grace: AsyncClient,
        library: dict[str, str],
        run_worker: Callable[[], Awaitable[None]],
    ) -> None:
        mine = await note(grace, "Grace", "Vector search cosine similarity notes by Grace.")
        await run_worker()
        body = (await grace.post(SEARCH, json={"query": "vector search cosine similarity"})).json()
        assert {r["document_id"] for r in body["results"]} == {mine}
        # Naming another user's document does not reveal it either.
        leaked = (
            await grace.post(SEARCH, json={"query": "vector", "document_ids": [library["pdf"]]})
        ).json()
        assert leaked["results"] == []

    async def test_user_id_in_the_body_is_rejected(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        response = await ada.post(
            SEARCH, json={"query": "vector", "user_id": "00000000-0000-0000-0000-000000000000"}
        )
        assert response.status_code == 422
        assert any("user_id" in e["loc"] for e in response.json()["errors"])

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(SEARCH, json={"query": "vector"})
        assert response.status_code == 401

    async def test_rejects_cross_site_requests(self, ada: AsyncClient) -> None:
        response = await ada.post(
            SEARCH, json={"query": "vector"}, headers={"Origin": "https://evil.example"}
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "body",
        [
            {"query": ""},
            {"query": "   "},
            {"query": "x" * 2001},
            {"query": "ok", "top_k": 0},
            {"query": "ok", "top_k": 51},
            {"query": "ok", "document_ids": ["not-a-uuid"]},
        ],
    )
    async def test_validates_input(self, ada: AsyncClient, body: dict[str, object]) -> None:
        assert (await ada.post(SEARCH, json=body)).status_code == 422


class TestIngestionStoresEmbeddings:
    async def test_every_chunk_has_an_embedding_and_the_model_is_recorded(
        self, library: dict[str, str], database: Database
    ) -> None:
        async with database.sessionmaker() as session:
            missing = await session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.embedding.is_(None))
            )
            models = set((await session.scalars(select(Document.embedding_model).distinct())).all())
            vector = await session.scalar(select(Chunk.embedding).limit(1))
        assert missing == 0
        assert models == {"fake-bow"}
        assert vector is not None
        assert len(vector) == 1024

    async def test_reindex_queues_documents_from_another_model(
        self, library: dict[str, str], database: Database, settings: Settings
    ) -> None:
        async with database.sessionmaker() as session:
            await session.execute(
                update(Document)
                .where(Document.id == library["pdf"])
                .values(embedding_model="some-older-model")
            )
            await session.commit()
        async with database.sessionmaker() as session:
            queued = await queue_stale_embeddings(
                session, embedding_model="fake-bow", max_attempts=settings.job_max_attempts
            )
        assert queued == 1
        async with database.sessionmaker() as session:
            job = await session.scalar(select(jobs.Job).where(jobs.Job.status == jobs.QUEUED))
            status = await session.scalar(
                select(Document.status).where(Document.id == library["pdf"])
            )
        assert job is not None
        assert str(job.resource_id) == library["pdf"]
        assert status == "pending"
