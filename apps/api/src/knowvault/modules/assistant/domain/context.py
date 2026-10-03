"""Choosing the sources an answer may use."""

from collections.abc import Sequence

from knowvault.modules.assistant.domain.model import Passage, Source


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def select_sources(
    passages: Sequence[Passage], *, max_sources: int, max_chars: int
) -> list[Source]:
    """Picks passages in relevance order within a character budget and numbers them.

    Passages with the same text as an earlier one are skipped, and a passage that does not fit
    the remaining budget is skipped in favour of shorter, less relevant ones. The chosen
    passages are grouped by document (documents in order of their best passage) and ordered by
    position within each document, so the model reads every document in its own order.
    Each source is exactly one chunk: `[n]` maps to one passage.
    """
    chosen: list[Passage] = []
    seen: set[str] = set()
    used = 0
    for passage in passages:
        if len(chosen) == max_sources:
            break
        key = _normalized(passage.content)
        if not key or key in seen or used + len(passage.content) > max_chars:
            continue
        seen.add(key)
        chosen.append(passage)
        used += len(passage.content)

    document_order: dict[object, int] = {}
    for passage in chosen:
        document_order.setdefault(passage.document_id, len(document_order))
    chosen.sort(key=lambda p: (document_order[p.document_id], p.ordinal))
    return [Source(ordinal, passage) for ordinal, passage in enumerate(chosen, start=1)]
