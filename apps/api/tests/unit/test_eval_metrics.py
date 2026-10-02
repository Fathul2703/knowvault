"""Ranking metrics used by the retrieval evaluation."""

import math

import pytest

from knowvault.evaluation.metrics import first_relevant_rank, mrr_at, percentile, success_at


def test_first_relevant_rank() -> None:
    assert first_relevant_rank([False, True, True]) == 2
    assert first_relevant_rank([False, False]) is None
    assert first_relevant_rank([]) is None


def test_success_at_counts_questions_with_a_hit_in_the_top_k() -> None:
    ranks = [1, 3, 7, None]
    assert success_at(ranks, 1) == 0.25
    assert success_at(ranks, 5) == 0.5
    assert success_at(ranks, 10) == 0.75
    assert success_at([], 5) == 0.0


def test_mrr_ignores_ranks_beyond_the_cutoff() -> None:
    ranks = [1, 2, 20, None]
    assert mrr_at(ranks, 10) == pytest.approx((1 + 0.5) / 4)
    assert mrr_at([], 10) == 0.0


def test_percentile_uses_nearest_rank() -> None:
    values = [40.0, 10.0, 30.0, 20.0]
    assert percentile(values, 50) == 20.0
    assert percentile(values, 95) == 40.0
    assert percentile(values, 0) == 10.0
    assert math.isnan(percentile([], 50))
