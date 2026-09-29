"""Embedding model adapters."""

from knowvault.adapters.embeddings.bge_m3 import BgeM3Embeddings
from knowvault.adapters.embeddings.fake import FakeEmbeddings
from knowvault.core.config import Settings
from knowvault.core.embeddings import EmbeddingModel


def build_embedding_model(settings: Settings) -> EmbeddingModel:
    if settings.embedding_provider == "fake":
        return FakeEmbeddings()
    return BgeM3Embeddings(
        settings.embedding_cache_dir,
        threads=settings.embedding_threads,
        batch_size=settings.embedding_batch_size,
    )


__all__ = ["BgeM3Embeddings", "FakeEmbeddings", "build_embedding_model"]
