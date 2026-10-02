# ADR 0006: Hybrid search with Reciprocal Rank Fusion

- Status: Accepted; query parsing and full-text ranking amended by ADR 0008
- Date: 2026-09-30

## Context

Vector search (ADR 0005) finds paraphrases and works across languages, but it is weak on exact
tokens. On the development data, the bge-m3 similarity of the query `ERR_4711` to a note that
contains `ERR_4711` was 0.571, and to a note that contains only `ERR_4712` it was 0.569 —
practically a tie. Names, codes, numbers and rare terms need keyword matching. The architecture
(§10.2) plans a hybrid of vector search and PostgreSQL full-text search fused with RRF.

## Decision

- **Full-text index:** `chunks.content_tsv` is a stored generated column,
  `to_tsvector('simple', content)`, with a GIN index (migration 0004). Being generated, it
  covers existing chunks without re-processing. The `simple` configuration (no stemming, no
  stop words) is language-neutral for mixed Indonesian and English text; the name is shared by
  index and queries through `core.text_search.FULLTEXT_CONFIG`.
- **Query parsing:** `websearch_to_tsquery`, which supports quoted phrases, `-exclusion` and
  `OR`, treats everything else as plain words and never raises on user input. Ranking:
  `ts_rank_cd` with normalisation 32 (values in [0, 1)).
- **Fusion:** Reciprocal Rank Fusion with k = 60 over the top 30 candidates of each method
  (or `top_k`, if larger), implemented as a pure domain function. Only ranks are used, so
  cosine similarity and `ts_rank_cd` never need to be normalised against each other. Ties are
  broken by best individual rank, then id.
- **API:** `POST /api/v1/retrieval/search` takes `mode`: `hybrid` (default), `vector` or
  `fulltext`. Each result reports `score` (RRF, cosine or ts_rank, depending on the mode),
  `similarity` (cosine to the query), `vector_rank` and `fulltext_rank`.
- **Similarity for every hybrid result.** Chunks found only by full-text search get their
  cosine similarity with one extra query, so callers always have an absolute relevance signal
  (the RRF score is not one). Phase 4's evidence gate can build on it.
- **Full-text mode does not embed the query**, so it works before the model is loaded.
- Full-text candidates are not restricted to the current embedding model: keyword search keeps
  working for documents waiting to be re-embedded. Such results have no similarity.

## Consequences

- The default `score` is now an RRF score instead of cosine similarity; `similarity` carries
  the cosine value. No client depended on the old meaning.
- Queries without shared words (for example Indonesian questions over English documents) get
  no full-text candidates, and hybrid results equal vector results.
- `simple` does not stem: "documents" does not match "document". Language-specific
  configurations can be evaluated once the retrieval evaluation harness exists.
- Two queries per search instead of one (plus a small one for missing similarities); measured
  well under 0.5 s on the development stack once the model is loaded.
