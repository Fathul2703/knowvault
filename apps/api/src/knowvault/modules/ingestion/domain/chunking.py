"""Structure-aware chunking.

The document text is the normalised blocks joined by blank lines. It is cut into *pieces*
(whole paragraphs; sentences of long paragraphs; hard splits of overlong sentences), and
consecutive pieces are packed into chunks of about `target_chars`:

* a chunk never spans two sections (different heading paths);
* a chunk never exceeds `max_chars`;
* consecutive chunks of a section share up to `overlap_chars` of whole pieces, so a sentence
  cut at a chunk boundary is still retrievable with its context;
* every piece belongs to at least one chunk, so no text is lost.

Sizes are measured in characters; for embedding models this is a conservative proxy for tokens.
"""

import re
from dataclasses import dataclass

from knowvault.modules.ingestion.domain.model import Block, ChunkDraft

BLOCK_SEPARATOR = "\n\n"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ChunkingConfig:
    target_chars: int = 1800
    max_chars: int = 2400
    overlap_chars: int = 200

    def __post_init__(self) -> None:
        if not 0 <= self.overlap_chars < self.target_chars <= self.max_chars:
            raise ValueError("expected 0 <= overlap_chars < target_chars <= max_chars")


@dataclass(frozen=True)
class _Piece:
    start: int
    end: int
    page: int | None
    section: int
    heading_path: tuple[str, ...]

    @property
    def length(self) -> int:
        return self.end - self.start


def join_blocks(blocks: list[Block]) -> str:
    return BLOCK_SEPARATOR.join(block.text for block in blocks)


def _hard_split(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Splits [start, end) into spans of at most max_chars, preferring to cut at spaces."""
    spans = []
    while end - start > max_chars:
        cut = text.rfind(" ", start + max_chars // 2, start + max_chars)
        if cut == -1:
            cut = start + max_chars
        spans.append((start, cut))
        start = cut
        while start < end and text[start] == " ":
            start += 1
    if start < end:
        spans.append((start, end))
    return spans


def _split_block(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    if end - start <= max_chars:
        return [(start, end)]
    spans: list[tuple[int, int]] = []
    sentence_start = start
    for match in _SENTENCE_BOUNDARY.finditer(text, start, end):
        spans.extend(_hard_split(text, sentence_start, match.start(), max_chars))
        sentence_start = match.end()
    spans.extend(_hard_split(text, sentence_start, end, max_chars))
    return spans


def _pieces(blocks: list[Block], text: str, max_chars: int) -> list[_Piece]:
    pieces: list[_Piece] = []
    offset = 0
    section = 0
    previous_path: tuple[str, ...] | None = None
    for block in blocks:
        if previous_path is not None and block.heading_path != previous_path:
            section += 1
        previous_path = block.heading_path
        block_end = offset + len(block.text)
        pieces.extend(
            _Piece(s, e, block.page, section, block.heading_path)
            for s, e in _split_block(text, offset, block_end, max_chars)
        )
        offset = block_end + len(BLOCK_SEPARATOR)
    return pieces


def chunk_blocks(blocks: list[Block], config: ChunkingConfig | None = None) -> list[ChunkDraft]:
    config = config or ChunkingConfig()
    text = join_blocks(blocks)
    pieces = _pieces(blocks, text, config.max_chars)
    drafts: list[ChunkDraft] = []

    i = 0
    covered_until = 0  # index of the first piece not yet in any chunk
    while i < len(pieces):
        first_new = max(i, covered_until)
        chunk_start = pieces[i].start
        j = i
        while j < len(pieces) and pieces[j].section == pieces[i].section:
            if j > first_new and pieces[j].end - chunk_start > config.target_chars:
                break
            j += 1

        members = pieces[i:j]
        pages = [p.page for p in members if p.page is not None]
        drafts.append(
            ChunkDraft(
                ordinal=len(drafts),
                content=text[chunk_start : members[-1].end],
                char_start=chunk_start,
                char_end=members[-1].end,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                heading_path=pieces[i].heading_path,
            )
        )
        covered_until = j
        if j >= len(pieces):
            break
        if pieces[j].section != pieces[j - 1].section:
            i = j
            continue

        # Step back over whole pieces that fit in the overlap budget. `k - 1 > i` guarantees
        # the next chunk starts after this one, so the loop always makes progress.
        k = j
        while (
            k - 1 > i
            and pieces[k - 1].section == pieces[j].section
            and pieces[j - 1].end - pieces[k - 1].start <= config.overlap_chars
        ):
            k -= 1
        if pieces[j].end - pieces[k].start > config.target_chars:
            k = j
        i = k
    return drafts
