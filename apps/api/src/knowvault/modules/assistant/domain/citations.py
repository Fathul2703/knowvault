"""Citation markers in answers: `[1]`, `[2][3]` or `[2, 3]`."""

import re
from dataclasses import dataclass

_MARKER = re.compile(r"\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,;:!?])")


@dataclass(frozen=True)
class CitationCheck:
    # Source numbers the answer cites that exist, ascending.
    cited: tuple[int, ...]
    # Numbers that refer to no source given to the model, ascending.
    invalid: tuple[int, ...]


def check_citations(text: str, source_count: int) -> CitationCheck:
    """Which `[n]` markers refer to one of the `source_count` sources.

    This guarantees only that citations point at real sources, not that a source supports the
    sentence citing it; that is measured by the answer evaluation.
    """
    numbers = {
        int(number) for match in _MARKER.finditer(text) for number in match.group(1).split(",")
    }
    return CitationCheck(
        cited=tuple(sorted(n for n in numbers if 1 <= n <= source_count)),
        invalid=tuple(sorted(n for n in numbers if not 1 <= n <= source_count)),
    )


def strip_citations(text: str) -> str:
    """Removes markers, e.g. from earlier answers whose numbers refer to other sources."""
    without = _MARKER.sub("", text)
    return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", without).strip()
