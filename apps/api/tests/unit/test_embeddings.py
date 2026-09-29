"""Embedding adapters and embedding text."""

import math
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from knowvault.adapters.embeddings import BgeM3Embeddings, FakeEmbeddings, build_embedding_model
from knowvault.core.config import Environment, Settings
from knowvault.core.embeddings import EMBEDDING_DIMENSIONS
from knowvault.modules.ingestion.domain.chunking import embedding_text
from knowvault.modules.ingestion.domain.model import ChunkDraft

DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class TestFakeEmbeddings:
    async def test_vectors_are_normalised_and_deterministic(self) -> None:
        model = FakeEmbeddings()
        first, second = await model.embed_documents(["Hybrid search", "Hybrid search"])
        assert len(first) == EMBEDDING_DIMENSIONS
        assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0)
        assert first == second
        assert await model.embed_query("Hybrid search") == first

    async def test_shared_words_mean_higher_similarity(self) -> None:
        model = FakeEmbeddings()
        query = await model.embed_query("vector search with pgvector")
        related, unrelated = await model.embed_documents(
            ["pgvector makes vector search fast", "nasi goreng dengan kecap manis"]
        )
        assert cosine(query, related) > cosine(query, unrelated)

    async def test_empty_text_still_gives_a_unit_vector(self) -> None:
        [vector] = await FakeEmbeddings().embed_documents(["   "])
        assert math.isclose(sum(v * v for v in vector), 1.0)


def test_factory_follows_settings(tmp_path: Path) -> None:
    fake = Settings(database_url=DB_URL, embedding_provider="fake")
    real = Settings(database_url=DB_URL, embedding_cache_dir=tmp_path)
    assert isinstance(build_embedding_model(fake), FakeEmbeddings)
    model = build_embedding_model(real)
    assert isinstance(model, BgeM3Embeddings)
    assert model.model_id.startswith("BAAI/bge-m3:int8@")
    assert model.dimensions == EMBEDDING_DIMENSIONS
    assert not any(tmp_path.iterdir())  # building the adapter downloads nothing


def test_fake_embeddings_are_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="tests only"):
        Settings(
            database_url=DB_URL,
            environment=Environment.PRODUCTION,
            session_cookie_secure=True,
            app_origin="https://knowvault.example",
            embedding_provider="fake",
        )


def test_embedding_text_adds_title_and_headings() -> None:
    chunk = ChunkDraft(
        ordinal=0,
        content="It returns the top-k results.",
        char_start=0,
        char_end=29,
        page_start=None,
        page_end=None,
        heading_path=("API", "Search"),
    )
    assert embedding_text("KnowVault guide", chunk) == (
        "KnowVault guide > API > Search\n\nIt returns the top-k results."
    )


REAL_MODEL_DIR = os.environ.get("KNOWVAULT_TEST_MODEL_DIR")


@pytest.mark.skipif(
    not REAL_MODEL_DIR,
    reason="set KNOWVAULT_TEST_MODEL_DIR to a cache directory to test the real bge-m3 model",
)
async def test_real_bge_m3_ranks_across_languages() -> None:
    """bge-m3 is multilingual: an Indonesian query finds English and Indonesian passages."""
    assert REAL_MODEL_DIR is not None
    model = BgeM3Embeddings(Path(REAL_MODEL_DIR), threads=None, batch_size=4)
    passages = [
        "Retrieval augmented generation grounds answers in the user's own documents.",
        "Pembangkitan berbasis temu kembali menjawab berdasarkan dokumen milik pengguna.",
        "Resep nasi goreng: tumis bawang putih lalu tambahkan kecap manis.",
        "The stock market closed higher on Friday.",
    ]
    vectors = await model.embed_documents(passages)
    query = await model.embed_query("Bagaimana RAG menjawab dengan sumber dari dokumen?")
    assert all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)
    scores = [cosine(query, v) for v in vectors]
    assert min(scores[:2]) > max(scores[2:])
