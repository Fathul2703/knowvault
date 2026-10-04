"""Hybrid, vector and full-text modes of POST /api/v1/retrieval/search (fake embeddings)."""

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.worker import build_pipeline, run_once
from tests.conftest import RegisterFn

SEARCH = "/api/v1/retrieval/search"
MakeInvite = Callable[[], Awaitable[str]]


@pytest.fixture
def run_worker(settings: Settings, database: Database) -> Callable[[], Awaitable[None]]:
    pipeline = build_pipeline(settings, database)

    async def _run() -> None:
        while await run_once(database, pipeline, settings):
            pass

    return _run


async def note(client: AsyncClient, title: str, body: str) -> str:
    response = await client.post("/api/v1/notes", json={"title": title, "body_md": body})
    assert response.status_code == 201
    document_id: str = response.json()["id"]
    return document_id


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register(email="ada@example.com")
    return client


@pytest.fixture
async def notes(ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]) -> dict[str, str]:
    ids = {
        # Mentions the error code once among many other words.
        "incident": await note(
            ada,
            "Incident report",
            "During the nightly batch the importer stopped with error ERR_4711 after a "
            "connection timeout to the storage cluster; operators restarted the service, "
            "reviewed dashboards, rotated credentials and filed a follow-up ticket.",
        ),
        # Repeats a query word but not the code.
        "timeouts": await note(ada, "Timeouts", "Timeout timeout timeout: tuning timeout values."),
        "recipes": await note(ada, "Recipes", "Fried rice with garlic and sweet soy sauce."),
    }
    await run_worker()
    return ids


def ids(body: dict[str, object]) -> list[str]:
    results = body["results"]
    assert isinstance(results, list)
    return [r["document_id"] for r in results]


class TestModes:
    async def test_hybrid_is_the_default_and_reports_both_ranks(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        body = (await ada.post(SEARCH, json={"query": "ERR_4711 storage timeout"})).json()
        assert body["mode"] == "hybrid"
        assert body["embedding_model"] == "fake-bow"
        top = body["results"][0]
        # Only the incident note contains every query word; it leads the fused list. The
        # timeouts note shares one word of three, below the minimum match, so it is not a
        # keyword candidate.
        assert top["document_id"] == notes["incident"]
        assert top["fulltext_rank"] == 1
        assert top["vector_rank"] is not None
        assert top["similarity"] is not None
        scores = [r["score"] for r in body["results"]]
        assert scores == sorted(scores, reverse=True)

    async def test_fulltext_mode_matches_words_without_embedding(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        body = (await ada.post(SEARCH, json={"query": "ERR_4711", "mode": "fulltext"})).json()
        assert body["mode"] == "fulltext"
        assert body["embedding_model"] is None
        assert ids(body) == [notes["incident"]]
        [hit] = body["results"]
        assert hit["similarity"] is None
        assert hit["vector_rank"] is None
        assert hit["fulltext_rank"] == 1
        # Score = distinct query words matched (1) + ts_rank_cd (< 1).
        assert 1 < hit["score"] < 2

    async def test_fulltext_ranks_chunks_with_more_query_words_first(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        # The timeouts note repeats "timeout" four times; the incident note contains both
        # words once. Containing more of the query's words wins.
        body = (
            await ada.post(SEARCH, json={"query": "ERR_4711 timeout", "mode": "fulltext"})
        ).json()
        assert ids(body) == [notes["incident"], notes["timeouts"]]

    async def test_fulltext_matches_natural_questions(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        body = (
            await ada.post(
                SEARCH,
                json={"query": "What happened when the importer stopped?", "mode": "fulltext"},
            )
        ).json()
        assert ids(body) == [notes["incident"]]

    async def test_fulltext_ignores_a_single_incidental_shared_word(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        # Shares only "rice" (one of four content words) with the recipes note.
        body = (
            await ada.post(
                SEARCH,
                json={"query": "irrigation schedule for rice paddies", "mode": "fulltext"},
            )
        ).json()
        assert body["results"] == []

    async def test_vector_mode_has_no_fulltext_ranks(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        body = (await ada.post(SEARCH, json={"query": "garlic rice", "mode": "vector"})).json()
        assert ids(body)[0] == notes["recipes"]
        assert all(r["fulltext_rank"] is None for r in body["results"])
        assert body["results"][0]["score"] == body["results"][0]["similarity"]

    async def test_unknown_mode_is_rejected(self, ada: AsyncClient) -> None:
        response = await ada.post(SEARCH, json={"query": "x", "mode": "bm25"})
        assert response.status_code == 422


class TestFullTextQueries:
    @pytest.mark.parametrize(
        "query",
        [
            '"connection timeout"',  # phrase
            "timeout -fried",  # exclusion
            "garlic OR ERR_4711",  # alternation
            '"(unbalanced & | ! :* <->',  # tsquery operators are treated as plain text
        ],
    )
    async def test_web_search_syntax_never_errors(
        self, ada: AsyncClient, notes: dict[str, str], query: str
    ) -> None:
        response = await ada.post(SEARCH, json={"query": query, "mode": "fulltext"})
        assert response.status_code == 200

    async def test_phrase_and_exclusion_semantics(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        phrase = (
            await ada.post(SEARCH, json={"query": '"connection timeout"', "mode": "fulltext"})
        ).json()
        assert ids(phrase) == [notes["incident"]]
        excluded = (
            await ada.post(SEARCH, json={"query": "timeout -storage", "mode": "fulltext"})
        ).json()
        assert ids(excluded) == [notes["timeouts"]]

    async def test_query_without_words_falls_back_to_vector_results(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        fulltext = (await ada.post(SEARCH, json={"query": "?!", "mode": "fulltext"})).json()
        assert fulltext["results"] == []
        hybrid = (await ada.post(SEARCH, json={"query": "?!"})).json()
        assert hybrid["results"]
        assert all(r["fulltext_rank"] is None for r in hybrid["results"])


class TestScope:
    @pytest.fixture
    async def grace(
        self,
        app_client_factory: Callable[[], AsyncClient],
        make_invite: MakeInvite,
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

    @pytest.mark.parametrize("mode", ["hybrid", "vector", "fulltext"])
    async def test_other_users_documents_are_never_returned(
        self, grace: AsyncClient, notes: dict[str, str], mode: str
    ) -> None:
        body = (await grace.post(SEARCH, json={"query": "ERR_4711 timeout", "mode": mode})).json()
        assert body["results"] == []

    async def test_collection_filter_applies_to_fulltext(
        self, ada: AsyncClient, notes: dict[str, str]
    ) -> None:
        collection = (await ada.post("/api/v1/collections", json={"name": "Ops"})).json()
        await ada.patch(
            f"/api/v1/documents/{notes['timeouts']}", json={"collection_id": collection["id"]}
        )
        body = (
            await ada.post(
                SEARCH,
                json={"query": "timeout", "mode": "fulltext", "collection_id": collection["id"]},
            )
        ).json()
        assert ids(body) == [notes["timeouts"]]


async def test_reranker_reorders_hybrid_results(
    settings: Settings,
    database: Database,
    app_client_factory: Callable[[], AsyncClient],
    make_invite: MakeInvite,
    run_worker: Callable[[], Awaitable[None]],
) -> None:
    from knowvault.adapters.reranking import FakeReranker
    from knowvault.adapters.storage.filesystem import FilesystemStorage
    from knowvault.main import create_app

    app = create_app(
        settings, database, FilesystemStorage(settings.storage_dir), reranker=FakeReranker()
    )
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    ) as client:
        await client.post(
            "/api/v1/auth/register",
            json={
                "invite_code": await make_invite(),
                "email": "rerank@example.com",
                "password": "correct horse battery",
                "display_name": "R",
            },
        )
        incident = await note(client, "Incident", "The storage cluster timed out at night.")
        await note(client, "Recipes", "Fried rice with garlic.")
        await run_worker()

        body = (await client.post(SEARCH, json={"query": "storage cluster timed out"})).json()
        assert body["reranker"] == "fake-overlap"
        top = body["results"][0]
        assert top["document_id"] == incident
        assert top["rerank_score"] == 1.0
        vector = (await client.post(SEARCH, json={"query": "storage", "mode": "vector"})).json()
        assert vector["reranker"] is None
        assert all(r["rerank_score"] is None for r in vector["results"])
