"""Chat adapters: the offline fake and Claude over a mocked HTTP transport."""

import json

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from knowvault.adapters.chat import build_chat_models
from knowvault.adapters.chat.claude import AnthropicChatModel
from knowvault.adapters.chat.fake import FakeChatModel
from knowvault.core.chat import ChatMessage, ChatModelError, StreamEnd, TextDelta, TokenUsage
from knowvault.core.config import Environment, Settings

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


def sources_message(question: str, *sources: str) -> ChatMessage:
    blocks = "\n".join(
        f'<source index="{n}" title="T">\n{text}\n</source>' for n, text in enumerate(sources, 1)
    )
    return ChatMessage("user", f"<sources>\n{blocks}\n</sources>\n\nAnswer:\n{question}")


async def collect(model: object, messages: list[ChatMessage]) -> tuple[str, StreamEnd]:
    text = ""
    end: StreamEnd | None = None
    async for event in model.stream(system="s", messages=messages, max_tokens=100):  # type: ignore[attr-defined]
        if isinstance(event, TextDelta):
            text += event.text
        else:
            end = event
    assert end is not None
    return text, end


class TestFakeChatModel:
    async def test_quotes_and_cites_the_sources_sharing_words_with_the_question(self) -> None:
        message = sources_message(
            "How many days of annual leave?",
            "Recipes need garlic.",
            "# Leave\nEmployees get twelve days of annual leave. Unused days expire.",
        )
        text, end = await collect(FakeChatModel(), [message])
        assert text == (
            "According to your documents: Employees get twelve days of annual leave. [2]"
        )
        assert end.stop_reason == "end_turn"
        assert end.usage.output_tokens > 0

    async def test_no_shared_words_means_no_answer(self) -> None:
        message = sources_message("Who won the football match?", "Recipes need garlic.")
        text, _ = await collect(FakeChatModel(), [message])
        assert text == "NO_ANSWER"

    async def test_complete_returns_the_last_line(self) -> None:
        completion = await FakeChatModel().complete(
            system="s",
            messages=[ChatMessage("user", "Conversation:\nUser: a\n\nFollow-up:\nAnd b?")],
            max_tokens=10,
        )
        assert completion.text == "And b?"


def stream_body(*texts: str, stop_reason: str = "end_turn") -> bytes:
    events: list[tuple[str, dict[str, object]]] = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-5-5",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 25, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        *(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                },
            )
            for text in texts
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 7},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events).encode()


def claude(handler: httpx2.MockTransport) -> AnthropicChatModel:
    client = anthropic.AsyncAnthropic(
        api_key="test-key", max_retries=0, http_client=httpx2.AsyncClient(transport=handler)
    )
    return AnthropicChatModel(client, "claude-sonnet-5-5")


class TestAnthropicChatModel:
    async def test_streams_text_then_usage(self) -> None:
        requests: list[dict[str, object]] = []

        def handle(request: httpx2.Request) -> httpx2.Response:
            requests.append(json.loads(request.content))
            return httpx2.Response(
                200,
                content=stream_body("Twelve ", "days [1]."),
                headers={"content-type": "text/event-stream"},
            )

        model = claude(httpx2.MockTransport(handle))
        text, end = await collect(model, [ChatMessage("user", "How many days?")])

        assert text == "Twelve days [1]."
        assert end == StreamEnd(TokenUsage(25, 7), "end_turn")
        [sent] = requests
        assert sent["model"] == "claude-sonnet-5-5"
        assert sent["system"] == "s"
        assert sent["max_tokens"] == 100
        assert sent["messages"] == [{"role": "user", "content": "How many days?"}]

    async def test_complete(self) -> None:
        def handle(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                200,
                json={
                    "id": "msg_2",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-haiku-4-5-20251001",
                    "content": [{"type": "text", "text": "How many holiday days?"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 40, "output_tokens": 6},
                },
            )

        completion = await claude(httpx2.MockTransport(handle)).complete(
            system="s", messages=[ChatMessage("user", "q")], max_tokens=50
        )
        assert completion.text == "How many holiday days?"
        assert completion.usage == TokenUsage(40, 6)

    @pytest.mark.parametrize(
        ("status", "code"),
        [(429, "llm_rate_limited"), (529, "llm_unavailable"), (500, "llm_unavailable")],
    )
    async def test_provider_errors_become_chat_model_errors(self, status: int, code: str) -> None:
        def handle(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                status, json={"type": "error", "error": {"type": "x", "message": "secret prompt"}}
            )

        with pytest.raises(ChatModelError) as caught:
            await collect(claude(httpx2.MockTransport(handle)), [ChatMessage("user", "q")])
        assert caught.value.code == code
        assert "secret prompt" not in caught.value.detail


class TestSettings:
    def test_fake_is_the_default(self) -> None:
        models = build_chat_models(Settings(database_url=DATABASE_URL))
        assert models.answer.model_id == "fake-extractive"

    def test_anthropic_needs_a_key(self) -> None:
        with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
            Settings(database_url=DATABASE_URL, llm_provider="anthropic")

    def test_anthropic_models(self) -> None:
        settings = Settings(
            database_url=DATABASE_URL, llm_provider="anthropic", anthropic_api_key="k"
        )
        models = build_chat_models(settings)
        assert models.answer.model_id == "claude-sonnet-5-5"
        assert models.fast.model_id == "claude-haiku-4-5-20251001"

    def test_production_refuses_the_fake(self) -> None:
        with pytest.raises(ValidationError, match="LLM_PROVIDER=fake"):
            Settings(
                database_url=DATABASE_URL,
                environment=Environment.PRODUCTION,
                session_cookie_secure=True,
                app_origin="https://kv.example.com",
                embedding_provider="bge-m3",
            )
