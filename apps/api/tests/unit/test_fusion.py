"""Reciprocal Rank Fusion."""

import uuid

import pytest

from knowvault.modules.retrieval.domain.fusion import RRF_K, reciprocal_rank_fusion

A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_single_list_keeps_its_order() -> None:
    fused = reciprocal_rank_fusion({"vector": [C, A, B]})
    assert [f.id for f in fused] == [C, A, B]
    assert fused[0].score == pytest.approx(1 / (RRF_K + 1))
    assert fused[0].ranks == {"vector": 1}


def test_agreement_between_lists_wins() -> None:
    # B is second in both lists; A and C are first in only one each.
    fused = reciprocal_rank_fusion({"vector": [A, B], "fulltext": [C, B]})
    assert fused[0].id == B
    assert fused[0].ranks == {"vector": 2, "fulltext": 2}
    assert fused[0].score == pytest.approx(2 / (RRF_K + 2))


def test_items_from_either_list_are_kept() -> None:
    fused = reciprocal_rank_fusion({"vector": [A], "fulltext": [D]})
    assert {f.id for f in fused} == {A, D}


def test_ties_are_broken_deterministically() -> None:
    first = reciprocal_rank_fusion({"vector": [A, B], "fulltext": [B, A]})
    second = reciprocal_rank_fusion({"fulltext": [B, A], "vector": [A, B]})
    assert [f.id for f in first] == [f.id for f in second] == [A, B]


def test_duplicates_in_one_list_count_once() -> None:
    fused = reciprocal_rank_fusion({"vector": [A, A, B]})
    assert fused[0].score == pytest.approx(1 / (RRF_K + 1))
    assert fused[0].ranks == {"vector": 1}


def test_k_controls_how_much_top_ranks_dominate() -> None:
    # B is fourth in both lists; A is first in one list only.
    fillers = [uuid.UUID(int=i) for i in range(10, 16)]
    rankings = {"vector": [A, *fillers[:2], B], "fulltext": [C, *fillers[2:4], B]}
    # Large k (default): agreement wins. 2 / (60 + 4) > 1 / (60 + 1).
    assert reciprocal_rank_fusion(rankings)[0].id == B
    # Small k: a single top rank wins. 1 / (1 + 1) > 2 / (1 + 4).
    assert reciprocal_rank_fusion(rankings, k=1)[0].id in {A, C}


def test_empty_input_and_invalid_k() -> None:
    assert reciprocal_rank_fusion({"vector": [], "fulltext": []}) == []
    with pytest.raises(ValueError, match="k must be"):
        reciprocal_rank_fusion({"vector": [A]}, k=0)
