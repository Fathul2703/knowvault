"""Text normalisation between extraction and chunking."""

import re
import unicodedata

from knowvault.modules.ingestion.domain.model import Block

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# "exam-\nple" → "example" when a word is split across lines (lowercase continuation only,
# so "well-\nKnown" and list dashes are left alone).
_HYPHENATION = re.compile(r"(\w)-\n(\w)")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n+")
_WHITESPACE = re.compile(r"\s+")


def _join_hyphenated(match: re.Match[str]) -> str:
    before, after = match.group(1), match.group(2)
    return before + after if after.islower() else match.group(0)


def normalize_text(text: str) -> list[str]:
    """Returns the paragraphs of `text`, each on a single line with collapsed whitespace."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = _CONTROL.sub("", text)
    text = _HYPHENATION.sub(_join_hyphenated, text)
    paragraphs = (_WHITESPACE.sub(" ", p).strip() for p in _PARAGRAPH_BREAK.split(text))
    return [p for p in paragraphs if p]


def normalize_blocks(blocks: list[Block]) -> list[Block]:
    """Splits blocks into single-paragraph blocks with clean text, dropping empty ones."""
    result: list[Block] = []
    for block in blocks:
        heading_path = tuple(
            h for h in (" ".join(normalize_text(h)) for h in block.heading_path) if h
        )
        result.extend(
            Block(text=paragraph, page=block.page, heading_path=heading_path)
            for paragraph in normalize_text(block.text)
        )
    return result
