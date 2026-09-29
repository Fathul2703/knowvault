"""Port for text embedding models. Implementations live in `knowvault.adapters.embeddings`."""

from typing import Protocol

# The `chunks.embedding` column is vector(EMBEDDING_DIMENSIONS). Changing it requires a
# migration and re-embedding every document (docs/ARCHITECTURE.md §7.6).
EMBEDDING_DIMENSIONS = 1024


class EmbeddingModel(Protocol):
    @property
    def model_id(self) -> str:
        """Identifies model and variant; stored with documents to detect stale embeddings."""
        ...

    @property
    def dimensions(self) -> int: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embeds passages for storage. Vectors are L2-normalised."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embeds a search query. The vector is L2-normalised."""
        ...
