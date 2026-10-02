"""Search requests and results."""

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

MAX_TOP_K = 50
# Candidates taken from each ranked list before fusion (at least top_k).
CANDIDATES_PER_LIST = 30


class SearchMode(StrEnum):
    HYBRID = "hybrid"  # vector + full text, fused with RRF
    VECTOR = "vector"  # cosine similarity only
    FULLTEXT = "fulltext"  # PostgreSQL full-text search only


@dataclass(frozen=True)
class SearchScope:
    """Which of the owner's documents to search. Empty filters mean "all ready documents"."""

    owner_id: uuid.UUID
    collection_id: uuid.UUID | None = None
    document_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChunkRecord:
    """A stored chunk with what a citation needs."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_kind: str
    ordinal: int
    content: str
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """A chunk found by one retrieval method, with that method's score."""

    chunk: ChunkRecord
    # Cosine similarity for vector search; for full-text search, distinct query words matched
    # plus ts_rank_cd (or ts_rank_cd alone for web-search syntax).
    value: float


@dataclass(frozen=True)
class SearchHit:
    chunk: ChunkRecord
    # Ordering score of the mode: RRF score (hybrid), cosine similarity (vector) or the
    # full-text value of the candidate (fulltext).
    score: float
    # Cosine similarity to the query, when the query was embedded and the chunk has a vector
    # from the current model.
    similarity: float | None
    # 1-based rank in each method's candidate list, when the chunk appeared there.
    vector_rank: int | None
    fulltext_rank: int | None
