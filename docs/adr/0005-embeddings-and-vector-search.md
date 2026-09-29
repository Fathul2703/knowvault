# ADR 0005: Embeddings (bge-m3 int8) and vector search

- Status: Accepted
- Date: 2026-09-30

## Context

Phase 3 needs dense embeddings for Indonesian and English text and a similarity search over
each user's chunks. D5 was decided as **BAAI/bge-m3, 1024 dimensions, run locally with ONNX
Runtime**. Two constraints shaped the details:

- fastembed 0.8 has no built-in bge-m3 model, so it is registered as a custom ONNX model.
- The development Docker VM has 4 GB of RAM, and the model is loaded by two processes (the
  API for queries, the worker for documents).

Measured on the development machine (Apple silicon, 4 threads, same texts):

| Variant | Peak RSS per process | 16 chunks × 1,800 chars | Cosine vs fp32 | Ranking vs fp32 |
|---|---|---|---|---|
| fp32 (BAAI/bge-m3 ONNX, 2.27 GB) | ~1.85 GB | 14.3 s | — | — |
| int8 (Xenova/bge-m3 `model_int8.onnx`, 569 MB) | ~1.13 GB | 5.3 s | 0.978–0.985 | identical |

The fp32 files also failed to load from the Hugging Face cache: ONNX Runtime 1.30 rejects
external weight data (`model.onnx_data`) that resolves, through the cache's symlinks, outside
the model directory.

## Decision

- **Model:** bge-m3, **int8** ONNX export from `Xenova/bge-m3` (MIT), pinned to revision
  `4de13258303883538bd53b696b452bf8099f0858`. Dense vector = normalised [CLS] embedding,
  1024 dimensions. Stored model id: `BAAI/bge-m3:int8@4de1325`.
- **Loading:** files are downloaded once with `snapshot_download(local_dir=…)` into a plain
  directory (`EMBEDDING_CACHE_DIR`, a volume shared by API and worker in Compose), then loaded
  through fastembed's `specific_model_path`. The model loads lazily on first use; inference runs
  in a thread so the event loop stays responsive. `knowvault download-model` pre-fetches it.
- **Port:** `core.embeddings.EmbeddingModel`; adapters `BgeM3Embeddings` and `FakeEmbeddings`
  (bag-of-words hashing, deterministic) for tests and CI. `EMBEDDING_PROVIDER=fake` is refused
  in production.
- **Storage:** `chunks.embedding vector(1024)` with an HNSW index (`vector_cosine_ops`, m=16,
  ef_construction=64); `documents.embedding_model` records which model embedded a document.
  The text embedded for a chunk is `title > heading > …` followed by the chunk content.
- **Search:** `POST /api/v1/retrieval/search` embeds the query, then orders the user's chunks
  by cosine distance. Only documents that are `ready` **and** embedded by the current model are
  searched (vectors of different models are not comparable). Per query: `hnsw.ef_search = 100`
  and `hnsw.iterative_scan = strict_order` (pgvector 0.8), so owner and collection filters
  applied after the index scan still return `top_k` rows.
- **The searching user comes from the session.** The request body may not name a user; an
  unknown field such as `user_id` is rejected with 422. Accepting a user id from the client
  would let any signed-in user search anyone's documents.
- **Module boundary:** `modules/retrieval` (api → infrastructure → application → domain) reads
  `chunks` and `documents` through read-only table definitions, not through the ingestion or
  library ORM models. Library and ingestion never import retrieval.
- **Existing data:** chunks from before this change have no embedding. `knowvault reindex`
  queues every ready document whose `embedding_model` differs from the current model.

## Consequences

- About 1 GB of RAM per process that uses the model; the full development stack fits in 4 GB.
- The first processed document or search after a fresh install waits for the 569 MB download
  unless `download-model` ran first.
- Changing the model or its variant means re-embedding everything (`knowvault reindex`); a
  different dimension also needs a migration.
- Tests and CI never download the model. An opt-in test (`KNOWVAULT_TEST_MODEL_DIR`) checks the
  real model's cross-lingual ranking.
- Hybrid search (full text + RRF), the search UI and the retrieval evaluation harness from the
  Phase 3 roadmap are not part of this change.
