"""Reranker adapters."""

from knowvault.adapters.reranking.bge_reranker import BgeReranker
from knowvault.adapters.reranking.fake import FakeReranker
from knowvault.core.config import Settings
from knowvault.core.reranker import Reranker


def build_reranker(settings: Settings) -> Reranker | None:
    if settings.reranker == "none":
        return None
    if settings.reranker == "fake":
        return FakeReranker()
    return BgeReranker(settings.embedding_cache_dir, threads=settings.embedding_threads)


__all__ = ["BgeReranker", "FakeReranker", "build_reranker"]
