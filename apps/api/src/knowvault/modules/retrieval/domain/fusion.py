"""Reciprocal Rank Fusion (Cormack, Clarke & Büttcher, 2009).

Each ranked list contributes 1 / (k + rank) for every item it contains (ranks start at 1). Only
ranks are used, so lists with incomparable scores — cosine similarity and ts_rank — can be
combined without normalisation. An item found by several lists accumulates their contributions.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# The constant from the original paper; it damps the advantage of the very top ranks.
RRF_K = 60


@dataclass(frozen=True)
class FusedItem:
    id: uuid.UUID
    score: float
    # Rank of the item in each list that contained it (1-based), keyed by list name.
    ranks: Mapping[str, int] = field(default_factory=dict)


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[uuid.UUID]], *, k: int = RRF_K
) -> list[FusedItem]:
    """Fuses ranked lists of ids, best first.

    Ties are broken by the best individual rank, then by id, so the order is deterministic.
    Duplicates within one list count once, at their best rank.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    scores: dict[uuid.UUID, float] = {}
    ranks: dict[uuid.UUID, dict[str, int]] = {}
    for name, ranking in rankings.items():
        for rank, item in enumerate(ranking, start=1):
            if name in ranks.get(item, {}):
                continue
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            ranks.setdefault(item, {})[name] = rank
    ordered = sorted(scores, key=lambda i: (-scores[i], min(ranks[i].values()), str(i)))
    return [FusedItem(id=i, score=scores[i], ranks=ranks[i]) for i in ordered]
