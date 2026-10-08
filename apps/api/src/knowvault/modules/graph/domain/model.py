"""Entities, mentions and relations extracted from chunks."""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import StrEnum


class EntityType(StrEnum):
    # Identifiers: error codes, item codes, version numbers, status codes.
    CODE = "code"
    # A proper name whose kind the extractor cannot tell (the heuristic extractor).
    NAME = "name"
    # Kinds a language-model extractor can assign.
    PERSON = "person"
    ORGANIZATION = "organization"
    PLACE = "place"
    PRODUCT = "product"
    CONCEPT = "concept"


# Relation between two entities mentioned in the same chunk, without a known meaning.
CO_OCCURS = "co_occurs"

_SPACE = re.compile(r"\s+")
_EDGE_PUNCTUATION = "\"'`.,;:!?()[]{}<>\u00ab\u00bb\u201c\u201d\u2018\u2019"


_SEPARATORS = re.compile(r"[-_/]+")


def _singular(word: str) -> str:
    """English plural endings removed: policies → policy, addresses → address, days → day.

    Only the key changes (names are shown as written), so an odd result for a word that only
    looks plural (Indonesian "kelas") harms nothing unless another name has that exact key.
    """
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_name(name: str, entity_type: EntityType) -> str:
    """The key that identifies an entity: same key, same entity (per owner and type).

    For names, case, hyphens and underscores, surrounding punctuation, repeated whitespace and
    an English plural on the last word do not matter ("Business Days" is "Business Day",
    "Retry-After" is "Retry After"). Codes keep their characters exactly (`ERR_4711` and
    `ERR-4711` stay different).
    """
    text = _SPACE.sub(" ", unicodedata.normalize("NFC", name)).strip().strip(_EDGE_PUNCTUATION)
    if entity_type is EntityType.CODE:
        return text.upper()
    words = _SEPARATORS.sub(" ", text.casefold()).split()
    if words:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def contains_other(a: str, b: str) -> bool:
    """True if all words of one name occur in the other ("Customer" and "Customer Data").

    Such names usually denote different, related things, so they are never merged by
    similarity: a wrong merge corrupts the graph, a missed one only leaves a duplicate.
    """
    words_a = set(normalize_name(a, EntityType.NAME).split())
    words_b = set(normalize_name(b, EntityType.NAME).split())
    return bool(words_a) and bool(words_b) and (words_a <= words_b or words_b <= words_a)


def may_merge(new_name: str, existing_name: str, similarity: float, threshold: float) -> bool:
    """Whether a newly found name is another way of writing an existing entity's name."""
    return similarity >= threshold and not contains_other(new_name, existing_name)


# Longest entity name looked up in a query, in words.
MAX_QUERY_NAME_WORDS = 6
_POSSESSIVE = re.compile(r"['\u2019]s$", re.IGNORECASE)


@dataclass(frozen=True)
class QueryKeys:
    """Entity keys that a query may mention, by kind of key."""

    names: frozenset[str]
    codes: frozenset[str]


def query_keys(query: str, max_words: int = MAX_QUERY_NAME_WORDS) -> QueryKeys:
    """The keys of every run of up to `max_words` words in the query.

    Looking these up finds the entities a query names without guessing which words are names:
    "how many business days does the Netherlands office need?" yields "business day" and
    "netherland office" among others, and only keys of existing entities match.
    """
    words = [
        _POSSESSIVE.sub("", word.strip(_EDGE_PUNCTUATION))
        for word in _SPACE.split(unicodedata.normalize("NFC", query))
    ]
    words = [word for word in words if word.strip(_EDGE_PUNCTUATION)]
    names: set[str] = set()
    codes: set[str] = set()
    for start in range(len(words)):
        for end in range(start + 1, min(len(words), start + max_words) + 1):
            text = " ".join(words[start:end])
            if name := normalize_name(text, EntityType.NAME):
                names.add(name)
            if end == start + 1:
                codes.add(normalize_name(text, EntityType.CODE))
    return QueryKeys(frozenset(names), frozenset(codes))


@dataclass(frozen=True)
class FoundEntity:
    """An entity as written in one chunk."""

    name: str
    type: EntityType
    # Occurrences in the chunk.
    count: int = 1

    @property
    def key(self) -> str:
        return normalize_name(self.name, self.type)


@dataclass(frozen=True)
class FoundRelation:
    source: FoundEntity
    target: FoundEntity
    type: str = CO_OCCURS


@dataclass(frozen=True)
class ChunkText:
    chunk_id: uuid.UUID
    text: str


@dataclass(frozen=True)
class ChunkGraph:
    """What an extractor found in one chunk."""

    chunk_id: uuid.UUID
    entities: list[FoundEntity] = field(default_factory=list)
    relations: list[FoundRelation] = field(default_factory=list)
