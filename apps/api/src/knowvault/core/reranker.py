"""Port for cross-encoder rerankers. Implementations live in `knowvault.adapters.reranking`."""

from typing import Protocol


class Reranker(Protocol):
    @property
    def model_id(self) -> str: ...

    async def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance of each passage to the query, in [0, 1], in the order given."""
        ...
