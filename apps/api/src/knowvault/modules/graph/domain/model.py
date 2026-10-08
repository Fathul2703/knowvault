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


def normalize_name(name: str, entity_type: EntityType) -> str:
    """The key that identifies an entity: same key, same entity (per owner and type).

    Case, surrounding punctuation and repeated whitespace do not matter; codes keep their
    characters exactly (`ERR_4711` and `ERR-4711` stay different).
    """
    text = _SPACE.sub(" ", unicodedata.normalize("NFC", name)).strip().strip(_EDGE_PUNCTUATION)
    return text.upper() if entity_type is EntityType.CODE else text.casefold()


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
