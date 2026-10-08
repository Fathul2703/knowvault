# ADR 0015: Knowledge graph — storage, extraction jobs and a rule-based extractor

- Status: Accepted
- Date: 2026-10-08

## Context

Phase 5 adds a knowledge graph: the entities a user's documents mention and how they relate,
stored in PostgreSQL rather than a separate graph database (docs/ARCHITECTURE.md §5). It will
later support entity resolution, a graph view and graph-augmented retrieval.

The architecture planned extraction with a language model and structured output, but there is
no API key during this phase. Extraction must therefore run offline by default, behind a port
that a model-based extractor can implement later.

## Decision

### Storage (migration 0006)

- **`entities`:** one row per owner, type and normalised name (unique), with the name as first
  written. Types are `code`, `name`, and `person`, `organization`, `place`, `product`, `concept`
  for extractors that can tell them apart.
- **`entity_mentions` (entity, chunk):** how often the entity occurs in the chunk, plus the
  document and owner for scoping.
- **`relations` (source, target, type, chunk):** the chunk is the evidence for the relation.
  `source` sorts before `target`, so an undirected relation is stored once per chunk.
- **Mentions and relations cascade with their chunks.** Reprocessing or deleting a document
  removes what was extracted from it. Each extraction then deletes the owner's entities that
  nothing mentions any more, and the API only shows entities with mentions in scope.

### Extraction as its own job

- **A hook in the ingestion pipeline.** Ingestion calls a `DocumentReadyHook` in the
  transaction that marks a document ready. The worker (composition root) wires it to queue an
  `extract_graph` job, so ingestion does not depend on the graph module, and the job exists only
  if the document really became ready.
- **The job:**
  - reads the chunks in a short transaction;
  - runs the extractor outside any transaction;
  - stores the result only if the document is still ready at the same content version, as
    processing does;
  - retries with backoff; after the last attempt it is marked dead and the document stays
    usable.
- **`GRAPH_EXTRACTOR=none`** disables the hook. `knowvault extract-graph` queues extraction for
  every ready document, which is the backfill after enabling it.

### The rule-based extractor (default)

- **Codes:**
  - identifiers with a separator and a digit (`ERR_4711`, `SKU-A1270`);
  - short letter-and-digit codes (`T30`);
  - three-part version numbers (`2.4.1`).
- **Names:** runs of up to five capitalised words, joined by connectors such as "of" or "dan".
  - A single capitalised word that starts a sentence is skipped.
  - Month and day names (English and Indonesian) and common sentence starters are not names.
  - Possessive endings are dropped.
  - Codes are never part of a name.
- **Relations:** entities in the same chunk co-occur (`co_occurs`). Each chunk keeps its 12 most
  frequent entities (`GRAPH_MAX_ENTITIES_PER_CHUNK`), which bounds the number of pairs.

### API (read-only)

- **`GET /api/v1/graph`:** the most mentioned entities, optionally within a collection or a
  document, and the relations among them, weighted by the number of passages.
- **`GET /api/v1/graph/entities/{id}`:** the passages mentioning an entity, with a snippet
  around the mention, and its most related entities.

Both are scoped to the signed-in user; another user's entity is 404.

## Consequences

- **Measured on the evaluation corpus** (31 documents): 69 entities, 107 mentions and 107
  relations; all 31 extraction jobs succeeded.
  - **What it finds:** codes (`ERR_4711`, `2.4.0`, `T30`), names (Master Services Agreement,
    Amsterdam, Netherlands) and technical terms (Retry-After, TLS).
  - **What it misses:** kinds of entity (everything that is not a code is a `name`), relation
    meanings, and lower-case concepts, which Indonesian text uses for most nouns.
- **Duplicates:** "Business Day" and "Business Days" are still separate entities; entity
  resolution is the next step.
- **Later extractors:** a model-based extractor (Claude, structured output) can replace the
  heuristic behind `EntityExtractor` once an API key is available. Its cost is per chunk, so it
  should stay optional.
