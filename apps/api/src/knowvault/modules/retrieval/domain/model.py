"""Search requests and results."""

import uuid
from dataclasses import dataclass, field

MAX_TOP_K = 50


@dataclass(frozen=True)
class SearchScope:
    """Which of the owner's documents to search. Empty filters mean "all ready documents"."""

    owner_id: uuid.UUID
    collection_id: uuid.UUID | None = None
    document_ids: tuple[uuid.UUID, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SearchHit:
    """One retrieved chunk with everything needed to cite it."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    document_kind: str
    ordinal: int
    content: str
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...]
    # Cosine similarity in [-1, 1]; higher is more similar.
    score: float
