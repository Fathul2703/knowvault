"""Conversations and streamed answers, end to end with fake embeddings and the fake model."""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select

from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.modules.assistant.domain.model import REFUSAL_TEXT
from knowvault.modules.assistant.infrastructure.models import Message, RetrievalTraceRecord
from knowvault.worker import build_pipeline, run_once
from tests.conftest import RegisterFn

CONVERSATIONS = "/api/v1/conversations"
LEAVE_QUESTION = "How many days of annual leave do employees get?"
UNRELATED_QUESTION = "Who won the football match yesterday?"

SseEvent = tuple[str, dict[str, object]]


def parse_sse(text: str) -> list[SseEvent]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def answer_text(events: list[SseEvent]) -> str:
    return "".join(str(data["text"]) for name, data in events if name == "token")


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


@pytest.fixture
async def library(ada: AsyncClient, run_worker: Callable[[], Awaitable[None]]) -> dict[str, str]:
    ids = {
        "leave": await note(
            ada,
            "Leave policy",
            "# Annual leave\n\nEmployees get twelve days of annual leave per year. Unused days "
            "expire at the end of March.",
        ),
        "recipes": await note(ada, "Recipes", "Fried rice needs garlic and sweet soy sauce."),
    }
    await run_worker()
    return ids


async def new_conversation(client: AsyncClient, **body: object) -> str:
    response = await client.post(CONVERSATIONS, json=body)
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["id"]
    return conversation_id


async def ask(client: AsyncClient, conversation_id: str, question: str) -> Response:
    return await client.post(
        f"{CONVERSATIONS}/{conversation_id}/messages", json={"content": question}
    )


class TestConversations:
    async def test_create_list_rename_delete(self, ada: AsyncClient) -> None:
        created = await ada.post(CONVERSATIONS, json={})
        assert created.status_code == 201
        body = created.json()
        assert body["title"] == ""
        assert body["scope"] == {"collection_id": None, "document_ids": []}

        listed = (await ada.get(CONVERSATIONS)).json()
        assert [c["id"] for c in listed["items"]] == [body["id"]]
        assert listed["next_cursor"] is None

        renamed = await ada.patch(f"{CONVERSATIONS}/{body['id']}", json={"title": " Leave "})
        assert renamed.json()["title"] == "Leave"

        assert (await ada.delete(f"{CONVERSATIONS}/{body['id']}")).status_code == 204
        assert (await ada.get(f"{CONVERSATIONS}/{body['id']}")).status_code == 404

    async def test_pagination_is_most_recent_first(self, ada: AsyncClient) -> None:
        ids = [await new_conversation(ada, title=f"c{i}") for i in range(3)]
        first = (await ada.get(CONVERSATIONS, params={"limit": 2})).json()
        second = (
            await ada.get(CONVERSATIONS, params={"limit": 2, "cursor": first["next_cursor"]})
        ).json()
        assert [c["id"] for c in first["items"] + second["items"]] == ids[::-1]
        assert second["next_cursor"] is None

    async def test_scope_must_belong_to_the_user(
        self,
        ada: AsyncClient,
        app_client_factory: Callable[[], AsyncClient],
        make_invite: Callable[[], Awaitable[str]],
    ) -> None:
        collection = (await ada.post("/api/v1/collections", json={"name": "HR"})).json()["id"]
        own = await new_conversation(ada, scope={"collection_id": collection})
        assert (await ada.get(f"{CONVERSATIONS}/{own}")).json()["scope"]["collection_id"] == (
            collection
        )

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
            stolen = await eve.post(CONVERSATIONS, json={"scope": {"collection_id": collection}})
            assert stolen.status_code == 404
            assert (await eve.get(f"{CONVERSATIONS}/{own}")).status_code == 404
            assert (await ask(eve, own, "What is in it?")).status_code == 404
            assert (await eve.delete(f"{CONVERSATIONS}/{own}")).status_code == 404
            assert (await eve.get(CONVERSATIONS)).json()["items"] == []

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(CONVERSATIONS)).status_code == 401
        assert (await client.post(CONVERSATIONS, json={})).status_code == 401

    @pytest.mark.parametrize(
        "body",
        [{"content": "   "}, {"content": "x" * 2001}, {"content": "q", "user_id": "someone"}],
    )
    async def test_question_validation(self, ada: AsyncClient, body: dict[str, object]) -> None:
        conversation = await new_conversation(ada)
        response = await ada.post(f"{CONVERSATIONS}/{conversation}/messages", json=body)
        assert response.status_code == 422


class TestAnswers:
    async def test_answer_streams_with_sources_and_is_stored_with_citations(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        conversation = await new_conversation(ada)
        response = await ask(ada, conversation, LEAVE_QUESTION)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(response.text)
        names = [name for name, _ in events]
        assert names[:2] == ["message.created", "sources"]
        assert names[-1] == "done"
        assert set(names[2:-1]) == {"token"}

        sources = events[1][1]["sources"]
        assert isinstance(sources, list)
        leave = next(s for s in sources if s["document_id"] == library["leave"])
        done = events[-1][1]
        assert done["status"] == "complete"
        assert done["citations"] == [leave["ordinal"]]
        assert done["invalid_citations"] == []
        assert f"[{leave['ordinal']}]" in answer_text(events)
        assert "twelve days" in answer_text(events)

        detail = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()
        assert detail["title"] == LEAVE_QUESTION
        question, answer = detail["messages"]
        assert (question["role"], question["content"]) == ("user", LEAVE_QUESTION)
        assert answer["role"] == "assistant"
        assert answer["status"] == "complete"
        assert answer["content"] == answer_text(events)
        assert answer["model_id"] == "fake-extractive"
        cited = [c for c in answer["citations"] if c["cited"]]
        assert [c["document_id"] for c in cited] == [library["leave"]]
        assert cited[0]["document_title"] == "Leave policy"
        assert cited[0]["heading_path"] == ["Annual leave"]
        assert "twelve days" in cited[0]["quoted_text"]
        assert len(answer["citations"]) == len(sources)

    async def test_question_outside_the_documents_is_refused(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        conversation = await new_conversation(ada)
        events = parse_sse((await ask(ada, conversation, UNRELATED_QUESTION)).text)

        assert events[-1][1]["status"] == "refused"
        assert events[-1][1]["citations"] == []
        assert answer_text(events) == REFUSAL_TEXT
        detail = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()
        assert detail["messages"][1]["status"] == "refused"
        assert detail["messages"][1]["content"] == REFUSAL_TEXT
        assert not any(c["cited"] for c in detail["messages"][1]["citations"])

    async def test_scope_without_documents_refuses_without_the_model(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        empty = (await ada.post("/api/v1/collections", json={"name": "Empty"})).json()["id"]
        conversation = await new_conversation(ada, scope={"collection_id": empty})

        events = parse_sse((await ask(ada, conversation, LEAVE_QUESTION)).text)

        assert events[1] == ("sources", {"sources": []})
        assert events[-1][1]["status"] == "refused"
        detail = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()
        assert detail["messages"][1]["model_id"] is None

    async def test_document_scope_limits_sources(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        conversation = await new_conversation(ada, scope={"document_ids": [library["recipes"]]})
        events = parse_sse((await ask(ada, conversation, LEAVE_QUESTION)).text)
        sources = events[1][1]["sources"]
        assert isinstance(sources, list)
        assert {s["document_id"] for s in sources} == {library["recipes"]}
        assert events[-1][1]["status"] == "refused"

    async def test_follow_up_keeps_history_and_a_trace(
        self, ada: AsyncClient, library: dict[str, str], database: Database
    ) -> None:
        conversation = await new_conversation(ada)
        await ask(ada, conversation, LEAVE_QUESTION)
        events = parse_sse((await ask(ada, conversation, "When do unused leave days expire?")).text)
        assert events[-1][1]["status"] == "complete"

        detail = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"] * 2
        async with database.sessionmaker() as session:
            traces = list(await session.scalars(select(RetrievalTraceRecord)))
        assert len(traces) == 2
        for trace in traces:
            assert trace.selected_chunk_ids
            assert trace.params["prompt_version"] == "answer-v1"
            assert {"chunk_id", "vector_rank", "fulltext_rank"} <= set(trace.candidates[0])

    async def test_citations_survive_deleting_the_document(
        self, ada: AsyncClient, library: dict[str, str]
    ) -> None:
        conversation = await new_conversation(ada)
        await ask(ada, conversation, LEAVE_QUESTION)
        assert (await ada.delete(f"/api/v1/documents/{library['leave']}")).status_code == 204

        answer = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()["messages"][1]
        [cited] = [c for c in answer["citations"] if c["cited"]]
        assert cited["chunk_id"] is None
        assert cited["document_id"] is None
        assert cited["document_title"] == "Leave policy"
        assert "twelve days" in cited["quoted_text"]

    async def test_deleting_a_conversation_deletes_its_messages(
        self, ada: AsyncClient, library: dict[str, str], database: Database
    ) -> None:
        conversation = await new_conversation(ada)
        await ask(ada, conversation, LEAVE_QUESTION)
        await ada.delete(f"{CONVERSATIONS}/{conversation}")
        async with database.sessionmaker() as session:
            assert await session.scalar(select(func.count()).select_from(Message)) == 0


class TestLimits:
    async def test_one_answer_at_a_time_per_user(
        self, ada: AsyncClient, library: dict[str, str], database: Database
    ) -> None:
        busy = await new_conversation(ada)
        other = await new_conversation(ada)
        await ask(ada, busy, LEAVE_QUESTION)
        async with database.sessionmaker() as session, session.begin():
            answer = await session.scalar(select(Message).where(Message.role == "assistant"))
            assert answer is not None
            answer.status = "streaming"

        blocked = await ask(ada, other, LEAVE_QUESTION)
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "answer_in_progress"

        # An answer left streaming by a process that died stops blocking after a while.
        async with database.sessionmaker() as session, session.begin():
            answer = await session.get(Message, answer.id)
            assert answer is not None
            answer.created_at = datetime.now(UTC) - timedelta(minutes=10)
        assert (await ask(ada, other, LEAVE_QUESTION)).status_code == 200

    async def test_daily_token_quota(
        self, ada: AsyncClient, library: dict[str, str], app: FastAPI, settings: Settings
    ) -> None:
        app.state.settings = settings.model_copy(update={"chat_daily_token_limit": 10})
        conversation = await new_conversation(ada)
        assert (await ask(ada, conversation, LEAVE_QUESTION)).status_code == 200

        refused = await ask(ada, conversation, LEAVE_QUESTION)
        assert refused.status_code == 429
        assert refused.json()["code"] == "token_quota_exceeded"
        assert int(refused.headers["Retry-After"]) > 0
        detail = (await ada.get(f"{CONVERSATIONS}/{conversation}")).json()
        assert len(detail["messages"]) == 2
