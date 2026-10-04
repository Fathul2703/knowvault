"""Reranker adapters and settings."""

import pytest
from pydantic import ValidationError

from knowvault.adapters.reranking import BgeReranker, FakeReranker, build_reranker
from knowvault.core.config import Environment, Settings

DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


async def test_fake_reranker_scores_word_overlap() -> None:
    scores = await FakeReranker().score(
        "annual leave days", ["Employees get annual leave days.", "Fried rice", ""]
    )
    assert scores == [1.0, 0.0, 0.0]


def test_no_reranker_by_default() -> None:
    assert build_reranker(Settings(database_url=DATABASE_URL)) is None


def test_bge_reranker_is_built_lazily(tmp_path: object) -> None:
    reranker = build_reranker(Settings(database_url=DATABASE_URL, reranker="bge-reranker-v2-m3"))
    assert isinstance(reranker, BgeReranker)
    # Nothing is downloaded or loaded until the first query.
    assert reranker.model_id.startswith("BAAI/bge-reranker-v2-m3:int8@")


def test_production_refuses_the_fake_reranker() -> None:
    with pytest.raises(ValidationError, match="RERANKER=fake"):
        Settings(
            database_url=DATABASE_URL,
            environment=Environment.PRODUCTION,
            session_cookie_secure=True,
            app_origin="https://kv.example.com",
            llm_provider="anthropic",
            anthropic_api_key="k",
            reranker="fake",
        )


def test_chunk_sizes_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP_CHARS < CHUNK_TARGET_CHARS"):
        Settings(database_url=DATABASE_URL, chunk_target_chars=1000, chunk_max_chars=800)
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP_CHARS < CHUNK_TARGET_CHARS"):
        Settings(database_url=DATABASE_URL, chunk_target_chars=500, chunk_overlap_chars=500)
    settings = Settings(
        database_url=DATABASE_URL,
        chunk_target_chars=1000,
        chunk_max_chars=1400,
        chunk_overlap_chars=150,
    )
    assert settings.chunk_target_chars == 1000
