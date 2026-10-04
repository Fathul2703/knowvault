# ADR 0013: Cross-encoder reranking — measured, available, not enabled

- Status: Accepted
- Date: 2026-10-04

## Context

The architecture postponed reranking until an evaluation could show its benefit (§10.2). The
harder dataset of Phase 5 (addendum to ADR 0007) left room for it: hybrid search ranked the
answer first for 85 of 95 answerable questions, with the rest at rank 2–4. A cross-encoder might
also give a better evidence threshold than cosine similarity, which does not separate answerable
from unanswerable questions (ADR 0007).

## Options considered

- **`jinaai/jina-reranker-v2-base-multilingual`**, which fastembed supports out of the box. Its
  licence is CC-BY-NC-4.0 (non-commercial), which does not fit a permissively licensed project.
  For the same reason PyMuPDF (AGPL) was avoided (D6).
- **English-only rerankers** (MS MARCO MiniLM, `bge-reranker-base`). Half the corpus and many
  questions are Indonesian.
- **`BAAI/bge-reranker-v2-m3`**: Apache-2.0, multilingual, and the same backbone as the bge-m3
  embeddings. It is used as the int8 ONNX export of the onnx-community organisation (571 MB),
  pinned to a revision like bge-m3 (ADR 0005), with the logits passed through a sigmoid.

## Decision

- **A `Reranker` port in `core`**, with the bge-reranker adapter and a deterministic fake for
  tests.
  - In hybrid mode, `SearchService` scores the first `RERANK_CANDIDATES` fused results (default
    10) and reorders them; ties keep the fused order.
  - The read-only transaction ends before the cross-encoder runs, so no database connection is
    held during inference.
  - Hits carry `rerank_score`, the search API reports the reranker, and answer traces record the
    scores.
  - The vector and full-text modes are never reranked.
- **The reranker is off by default** (`RERANKER=none`). It is a setting, so it can be switched on
  where the hardware makes its latency acceptable.
- **No evidence threshold before the model.** Refusing still relies on the empty-retrieval check
  and on the model's `NO_ANSWER` (ADR 0009).

## Measurements

Hybrid mode, 95 answerable questions, bge-m3 embeddings, CPU in Docker:

| | Success@1 | MRR@10 | Latency p50 | p95 | Report |
|---|---|---|---|---|---|
| Hybrid (RRF) | 89.5% | 0.941 | 71 ms | 94 ms | [baseline](../../eval/reports/2026-10-03-2039-retrieval-hard-questions.md) |
| + rerank top 20 | 91.6% | 0.953 | 4,173 ms | 5,623 ms | [report](../../eval/reports/2026-10-03-2110-retrieval-rerank-bge-v2-m3-top20.md) |
| + rerank top 10 | 91.6% | 0.953 | 2,488 ms | 4,406 ms | [report](../../eval/reports/2026-10-03-2115-retrieval-rerank-bge-v2-m3-top10.md) |

- **8 questions improve and 6 get worse.**
  - The gains are where the cross-encoder reads meaning: neighbouring documents (the
    postmortem against the runbook, the partner API against the public one), cross-lingual
    questions and a long document. Distractor and long-document MRR reach 1.000, cross-lingual
    MRR rises from 0.825 to 0.904.
  - The losses are on exact tokens: version `2.4.1`, status `T30`, the 2022 policy's rules and a
    retention period. Identifier MRR falls from 1.000 to 0.952 and version MRR from 1.000 to
    0.833, which undoes part of what full-text search added (ADR 0006, 0008).
- **Latency grows about 35-fold** with ten candidates, to 2.5 s for half the searches. That is
  too slow for the Search page, where results appear as you type and submit.
- **Answers would gain little.** The evidence is already among the eight sources given to the
  model for 95 of 95 questions; reordering changes their numbering, not what the model sees.
- **As an evidence threshold**, the best-scoring chunk separates the groups far better than
  cosine similarity. The unanswerable median is 0.002 against 0.91 for the first relevant
  chunk, but the tails overlap:

| Refuse below | Answerable refused (wrong) | Unanswerable refused (right) |
|---|---|---|
| 0.01 | 3 of 95 | 9 of 13 |
| 0.05 | 8 of 95 | 10 of 13 |
| 0.2 | 13 of 95 | 11 of 13 |

  The three answerable questions refused at 0.01 are all cross-lingual. The near-miss
  unanswerable questions score high (an "enterprise plan" 0.973, interns' leave 0.721): they
  look relevant and only a model reading the passage can tell they are not answered. Refusing
  answerable questions is the worse error for a knowledge base, so no threshold is used.

## Consequences

- Search and chat keep their speed; the reranker is one setting away
  (`RERANKER=bge-reranker-v2-m3`, `knowvault download-model` fetches it) for deployments with
  more CPU or a GPU.
- **Reconsider when** a GPU or faster cross-encoder brings the latency under about 300 ms, or
  when real libraries show a larger share of neighbouring-document mistakes than this corpus.
  A combination that keeps exact-token matches on top (for example reranking only results that
  full-text search did not rank first) would be the next experiment.
