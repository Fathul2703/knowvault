"""Rule-based entity extraction: no model, no network, deterministic.

It finds two kinds of entities that matter in a knowledge base and need no understanding:

- **Codes**: identifiers such as `ERR_4711`, `SKU-A1270`, `T30` and version numbers like
  `2.4.1`, which embeddings confuse with their neighbours.
- **Names**: runs of capitalised words that do not start a sentence ("Master Services
  Agreement", "Bekasi", "Retry-After"), in English and Indonesian.

Entities found in the same chunk are related by co-occurrence. A language-model extractor can
replace this behind the same port to add entity kinds and relation meanings.
"""

import re
from collections import Counter
from itertools import combinations

from knowvault.modules.graph.domain.model import (
    ChunkGraph,
    ChunkText,
    EntityType,
    FoundEntity,
    FoundRelation,
)

_CODE = re.compile(r"\b(?:[A-Z][A-Z0-9]*[_-][A-Z0-9]+(?:[_-][A-Z0-9]+)*|[A-Z]{1,3}\d{2,5})\b")
_VERSION = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])")
_SENTENCE = re.compile(r"(?<=[.!?:])\s+|\n+")
_TOKEN = re.compile(r"[\w][\w'\u2019&-]*", re.UNICODE)

# Capitalised for reasons other than being a name: sentence-like starts, months and days in
# English and Indonesian, and words that open headings or list items.
_NOT_NAMES = frozenset(
    [
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "we",
        "our",
        "you",
        "your",
        "they",
        "their",
        "he",
        "she",
        "i",
        "if",
        "when",
        "while",
        "after",
        "before",
        "for",
        "in",
        "on",
        "at",
        "by",
        "of",
        "to",
        "with",
        "from",
        "and",
        "or",
        "but",
        "not",
        "no",
        "yes",
        "all",
        "any",
        "each",
        "every",
        "some",
        "many",
        "most",
        "more",
        "less",
        "other",
        "such",
        "only",
        "also",
        "however",
        "because",
        "therefore",
        "during",
        "until",
        "since",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "januari",
        "februari",
        "maret",
        "mei",
        "juni",
        "juli",
        "agustus",
        "oktober",
        "desember",
        "senin",
        "selasa",
        "rabu",
        "kamis",
        "jumat",
        "sabtu",
        "minggu",
        "di",
        "ke",
        "dari",
        "dan",
        "atau",
        "yang",
        "untuk",
        "dengan",
        "pada",
        "dalam",
        "oleh",
        "jika",
        "bila",
        "saat",
        "setelah",
        "sebelum",
        "setiap",
        "semua",
        "kami",
        "kita",
        "anda",
        "mereka",
        "ini",
        "itu",
        "ada",
        "tidak",
        "bukan",
        "karena",
        "agar",
        "supaya",
        "rp",
        "note",
        "summary",
        "design",
        "notes",
    ]
)
_CONNECTORS = frozenset({"of", "and", "&", "dan", "for", "di", "de"})
_MAX_NAME_TOKENS = 5


def _is_capitalised(token: str) -> bool:
    return token[0].isupper() and token.casefold() not in _NOT_NAMES


def _codes(text: str) -> list[str]:
    found = [m.group(0) for m in _CODE.finditer(text)]
    # A code must contain a digit; "X-RateLimit-Limit" or "CEO" are not identifiers.
    found = [code for code in found if any(ch.isdigit() for ch in code)]
    return found + _VERSION.findall(text)


def _token(word: str) -> str:
    """A word without a possessive ending: "Provider's" is the Provider."""
    for ending in ("'s", "\u2019s"):
        if word.endswith(ending):
            return word[: -len(ending)]
    return word


def _names(text: str, codes: set[str]) -> list[str]:
    names: list[str] = []
    for sentence in _SENTENCE.split(text):
        tokens = [_token(m.group(0)) for m in _TOKEN.finditer(sentence.lstrip("#*-> \t"))]
        i = 0
        while i < len(tokens):
            if not _is_capitalised(tokens[i]) or tokens[i] in codes:
                i += 1
                continue
            j = i + 1
            while j < len(tokens) and j - i < _MAX_NAME_TOKENS:
                nxt = tokens[j]
                if nxt in codes:
                    break  # codes are entities of their own, never part of a name
                if _is_capitalised(nxt) or (nxt.isdigit() and len(nxt) >= 3):
                    j += 1
                elif (
                    nxt.casefold() in _CONNECTORS
                    and j + 1 < len(tokens)
                    and _is_capitalised(tokens[j + 1])
                ):
                    j += 2
                else:
                    break
            run = tokens[i:j]
            # A single capitalised word that starts the sentence is usually just that.
            if not (i == 0 and len(run) == 1) and len(" ".join(run)) >= 3:
                names.append(" ".join(run))
            i = j
    return names


def extract(chunk: ChunkText, *, max_entities: int = 12) -> ChunkGraph:
    """Entities of one chunk (the most frequent `max_entities`) and their co-occurrences."""
    codes = _codes(chunk.text)
    counts: Counter[tuple[str, EntityType]] = Counter()
    first_seen: dict[tuple[str, EntityType], str] = {}
    for name, entity_type in [(c, EntityType.CODE) for c in codes] + [
        (n, EntityType.NAME) for n in _names(chunk.text, set(codes))
    ]:
        key = (FoundEntity(name, entity_type).key, entity_type)
        counts[key] += 1
        first_seen.setdefault(key, name)

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0][0]))[:max_entities]
    entities = [FoundEntity(first_seen[key], key[1], count) for key, count in ranked]
    ordered = sorted(entities, key=lambda e: (e.type.value, e.key))
    relations = [FoundRelation(a, b) for a, b in combinations(ordered, 2)]
    return ChunkGraph(chunk.chunk_id, entities, relations)


class HeuristicExtractor:
    """The default extractor (`GRAPH_EXTRACTOR=heuristic`)."""

    def __init__(self, max_entities_per_chunk: int = 12) -> None:
        self._max = max_entities_per_chunk

    @property
    def name(self) -> str:
        return "heuristic-v1"

    async def extract(self, chunks: list[ChunkText]) -> list[ChunkGraph]:
        return [extract(chunk, max_entities=self._max) for chunk in chunks]
