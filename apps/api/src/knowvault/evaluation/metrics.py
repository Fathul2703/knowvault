"""Ranking metrics. Pure functions over the rank of the first relevant result per question."""

import math
from collections.abc import Sequence


def first_relevant_rank(relevance: Sequence[bool]) -> int | None:
    """1-based rank of the first relevant result, or None if none is relevant."""
    for rank, relevant in enumerate(relevance, start=1):
        if relevant:
            return rank
    return None


def success_at(ranks: Sequence[int | None], k: int) -> float:
    """Share of questions with a relevant result in the top k (often called hit rate@k)."""
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mrr_at(ranks: Sequence[int | None], k: int) -> float:
    """Mean reciprocal rank, counting only relevant results within the top k."""
    if not ranks:
        return 0.0
    return sum(1 / rank for rank in ranks if rank is not None and rank <= k) / len(ranks)


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (p in [0, 100]); NaN for an empty sequence."""
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, math.ceil(p / 100 * len(ordered)) - 1)
    return ordered[index]
