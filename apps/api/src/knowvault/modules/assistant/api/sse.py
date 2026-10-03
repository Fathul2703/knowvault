"""Server-Sent Events encoding of answer events (docs/ARCHITECTURE.md §8.3)."""

import json
from collections.abc import AsyncGenerator, AsyncIterator

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from knowvault.modules.assistant.application.answer import (
    AnswerDone,
    AnswerEvent,
    AnswerFailed,
    AnswerText,
    MessageCreated,
    SourcesFound,
)


def _frame(event: str, data: dict[str, object]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


def encode(event: AnswerEvent) -> bytes:
    match event:
        case MessageCreated():
            return _frame(
                "message.created",
                {
                    "conversation_id": str(event.conversation_id),
                    "user_message_id": str(event.user_message_id),
                    "message_id": str(event.message_id),
                },
            )
        case SourcesFound():
            return _frame(
                "sources",
                {
                    "sources": [
                        {
                            "ordinal": s.ordinal,
                            "chunk_id": str(s.passage.chunk_id),
                            "chunk_ordinal": s.passage.ordinal,
                            "document_id": str(s.passage.document_id),
                            "title": s.passage.document_title,
                            "page_start": s.passage.page_start,
                            "page_end": s.passage.page_end,
                            "heading_path": list(s.passage.heading_path),
                            "quoted_text": s.passage.content,
                        }
                        for s in event.sources
                    ]
                },
            )
        case AnswerText():
            return _frame("token", {"text": event.text})
        case AnswerDone():
            return _frame(
                "done",
                {
                    "message_id": str(event.message_id),
                    "status": event.status.value,
                    "citations": list(event.cited),
                    "invalid_citations": list(event.invalid),
                    "usage": {
                        "input_tokens": event.usage.input_tokens,
                        "output_tokens": event.usage.output_tokens,
                    },
                },
            )
        case AnswerFailed():
            return _frame(
                "error",
                {"message_id": str(event.message_id), "code": event.code, "detail": event.detail},
            )


async def _encoded(events: AsyncIterator[AnswerEvent]) -> AsyncIterator[bytes]:
    async for event in events:
        yield encode(event)


class EventStreamResponse(StreamingResponse):
    """Streams answer events and always closes the answer when the response ends.

    Starlette stops iterating when the client disconnects but leaves the generator suspended;
    closing it runs the answer's cleanup, which stores the answer as failed.
    """

    def __init__(self, events: AsyncGenerator[AnswerEvent]) -> None:
        super().__init__(
            _encoded(events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._events = events

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._events.aclose()
