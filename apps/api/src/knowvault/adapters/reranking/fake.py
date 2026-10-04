"""Deterministic reranker for tests: no model, no network."""

import re

_WORD = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


class FakeReranker:
    """Scores a passage by the share of the query's words it contains."""

    @property
    def model_id(self) -> str:
        return "fake-overlap"

    async def score(self, query: str, passages: list[str]) -> list[float]:
        wanted = _words(query)
        if not wanted:
            return [0.0 for _ in passages]
        return [len(wanted & _words(passage)) / len(wanted) for passage in passages]
