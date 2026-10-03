"""Claude through the Anthropic Messages API."""

from collections.abc import AsyncIterator

import anthropic
from anthropic.types import MessageParam

from knowvault.core.chat import (
    ChatMessage,
    ChatModelError,
    Completion,
    StreamEnd,
    TextDelta,
    TokenUsage,
)


def _params(messages: list[ChatMessage]) -> list[MessageParam]:
    return [{"role": m.role, "content": m.content} for m in messages]


def _error(exc: anthropic.AnthropicError) -> ChatModelError:
    # Only the error class and status reach logs and clients, never request content.
    if isinstance(exc, anthropic.APITimeoutError):
        return ChatModelError("llm_timeout", "The language model did not respond in time.")
    if isinstance(exc, anthropic.RateLimitError):
        return ChatModelError("llm_rate_limited", "The language model is rate limited.")
    if isinstance(exc, anthropic.APIStatusError):
        return ChatModelError(
            "llm_unavailable", f"The language model returned HTTP {exc.status_code}."
        )
    return ChatModelError("llm_unavailable", "The language model could not be reached.")


class AnthropicChatModel:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model_id(self) -> str:
        return self._model

    async def stream(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[TextDelta | StreamEnd]:
        # The SDK retries failed connection attempts; once the response has started, errors
        # are raised instead, so text is never repeated.
        try:
            async with self._client.messages.stream(
                model=self._model,
                system=system,
                messages=_params(messages),
                max_tokens=max_tokens,
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise _error(exc) from exc
        yield StreamEnd(
            TokenUsage(final.usage.input_tokens, final.usage.output_tokens), final.stop_reason
        )

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> Completion:
        try:
            message = await self._client.messages.create(
                model=self._model,
                system=system,
                messages=_params(messages),
                max_tokens=max_tokens,
            )
        except anthropic.AnthropicError as exc:
            raise _error(exc) from exc
        text = "".join(block.text for block in message.content if block.type == "text")
        return Completion(text, TokenUsage(message.usage.input_tokens, message.usage.output_tokens))
