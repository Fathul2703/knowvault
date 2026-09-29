"""Deterministic embeddings for tests: no model download, no network."""

import hashlib
import math
import re

from knowvault.core.embeddings import EMBEDDING_DIMENSIONS

_TOKEN = re.compile(r"\w+", re.UNICODE)


class FakeEmbeddings:
    """Bag-of-words feature hashing, L2-normalised.

    Texts that share words get similar vectors, so ranking behaviour can be tested without a
    real model. It captures no meaning beyond word overlap.
    """

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return "fake-bow"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
