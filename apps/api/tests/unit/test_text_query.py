"""Turning user queries into full-text expressions."""

import pytest

from knowvault.modules.retrieval.domain.text_query import (
    MAX_TERMS,
    FulltextQuery,
    fulltext_query,
    minimum_match,
    uses_web_search_syntax,
)


@pytest.mark.parametrize(
    "query",
    ['"connection timeout"', "timeout -storage", "garlic OR rice", "-only"],
)
def test_web_search_syntax_is_passed_through(query: str) -> None:
    assert uses_web_search_syntax(query)
    assert fulltext_query(query) == FulltextQuery(expression=query)


@pytest.mark.parametrize("query", ["read-only access", "garlic or rice", "ERR-42", "co-op"])
def test_hyphens_inside_words_and_lowercase_or_are_not_syntax(query: str) -> None:
    assert not uses_web_search_syntax(query)


def test_natural_questions_drop_stop_words_and_use_or() -> None:
    assert fulltext_query("How long are support conversations kept?") == FulltextQuery(
        expression="long OR support OR conversations OR kept",
        terms=("long", "support", "conversations", "kept"),
    )


def test_indonesian_stop_words_are_dropped() -> None:
    query = fulltext_query("Berapa lama rendang tahan di lemari pendingin?")
    assert query.terms == ("lama", "rendang", "tahan", "lemari", "pendingin")


def test_words_are_kept_whole_for_postgres_to_tokenise() -> None:
    query = fulltext_query("What does ERR_4711 mean in 2.3.2, and doctor's notes?")
    assert query.terms == ("ERR_4711", "mean", "2.3.2", "doctor's", "notes")


def test_duplicates_are_removed_and_order_kept() -> None:
    assert fulltext_query("timeout Timeout timeout").terms == ("timeout", "Timeout")


def test_stop_word_only_queries_still_search() -> None:
    assert fulltext_query("how are you").terms == ("how", "are", "you")


def test_queries_without_words_search_nothing() -> None:
    assert fulltext_query("?! …") == FulltextQuery(expression="", terms=())


def test_long_questions_are_capped() -> None:
    words = " ".join(f"word{i}" for i in range(40))
    assert len(fulltext_query(words).terms) == MAX_TERMS


@pytest.mark.parametrize(("count", "expected"), [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2), (5, 3)])
def test_minimum_match_is_half_rounded_up(count: int, expected: int) -> None:
    assert minimum_match(tuple(f"w{i}" for i in range(count))) == expected
