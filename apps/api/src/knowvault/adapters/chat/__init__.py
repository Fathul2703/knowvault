"""Chat model adapters."""

import anthropic

from knowvault.adapters.chat.claude import AnthropicChatModel
from knowvault.adapters.chat.fake import FakeChatModel
from knowvault.core.chat import ChatModels
from knowvault.core.config import Settings


def build_chat_models(settings: Settings) -> ChatModels:
    if settings.llm_provider == "fake":
        return ChatModels(answer=FakeChatModel(), fast=FakeChatModel())
    if settings.anthropic_api_key is None:  # also rejected by Settings validation
        raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )
    return ChatModels(
        answer=AnthropicChatModel(client, settings.llm_model),
        fast=AnthropicChatModel(client, settings.llm_fast_model),
    )


__all__ = ["AnthropicChatModel", "FakeChatModel", "build_chat_models"]
