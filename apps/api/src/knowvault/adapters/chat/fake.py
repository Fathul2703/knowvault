"""Offline chat model for development and tests: no API key, no network, deterministic.

It does not understand language. It relies on two conventions of the assistant's prompts:
the question is the last line of the last user message, and sources are wrapped in
`<source index="n" ...>` tags. Answers quote the first sentence of the sources that share the
most words with the question, cite them as `[n]`, and are `NO_ANSWER` when no source shares a
word with it.
"""

import re
from collections.abc import AsyncIterator

from knowvault.core.chat import (
    ChatMessage,
    Completion,
    StreamEnd,
    TextDelta,
    TokenUsage,
)

_SOURCE = re.compile(r'<source index="(\d+)"[^>]*>(.*?)</source>', re.DOTALL)
_WORD = re.compile(r"\w{4,}", re.UNICODE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
# Frequent question words that would otherwise match almost any source.
_IGNORED = frozenset(
    [
        "what",
        "which",
        "when",
        "where",
        "does",
        "have",
        "with",
        "from",
        "that",
        "this",
        "there",
        "their",
        "about",
        "apakah",
        "bagaimana",
        "berapa",
        "kapan",
        "siapa",
        "yang",
        "dengan",
        "untuk",
        "dari",
        "pada",
        "adalah",
        "harus",
        "bisa",
        "saya",
        "kami",
    ]
)
_MAX_SENTENCE = 240


def _words(text: str) -> set[str]:
    return {w for w in (m.lower() for m in _WORD.findall(text)) if w not in _IGNORED}


def _first_sentence(content: str) -> str:
    lines = [line.strip() for line in content.strip().splitlines()]
    body = " ".join(line for line in lines if line and not line.startswith("#"))
    sentence = _SENTENCE_END.split(body, maxsplit=1)[0]
    return sentence if len(sentence) <= _MAX_SENTENCE else sentence[:_MAX_SENTENCE].rstrip() + "…"


def _last_line(messages: list[ChatMessage]) -> str:
    users = [m.content for m in messages if m.role == "user"]
    lines = [line.strip() for line in users[-1].splitlines() if line.strip()] if users else []
    return lines[-1] if lines else ""


def _usage(messages: list[ChatMessage], system: str, output: str) -> TokenUsage:
    # Roughly four characters per token.
    prompt = len(system) + sum(len(m.content) for m in messages)
    return TokenUsage(prompt // 4, max(1, len(output) // 4))


class FakeChatModel:
    def __init__(self, model_id: str = "fake-extractive") -> None:
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def answer(self, messages: list[ChatMessage]) -> str:
        question = _words(_last_line(messages))
        sources = _SOURCE.findall(messages[-1].content) if messages else []
        scored = sorted(
            ((len(question & _words(content)), int(index), content) for index, content in sources),
            key=lambda item: (-item[0], item[1]),
        )
        picked = [item for item in scored if item[0] > 0][:2]
        if not picked:
            return "NO_ANSWER"
        parts = [f"{_first_sentence(content)} [{index}]" for _, index, content in picked]
        return "According to your documents: " + " ".join(parts)

    async def stream(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> AsyncIterator[TextDelta | StreamEnd]:
        text = self.answer(messages)
        for piece in re.findall(r"\S+\s*", text):
            yield TextDelta(piece)
        yield StreamEnd(_usage(messages, system, text), "end_turn")

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int
    ) -> Completion:
        # Used for query condensation: returns the follow-up question unchanged.
        text = _last_line(messages)
        return Completion(text, _usage(messages, system, text))
