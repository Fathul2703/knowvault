# Retrieval evaluation — 2026-10-03 (rerank-bge-v2-m3-top20)

Generated 2026-10-03 21:10 UTC by `knowvault eval-retrieval`.

## Setup

- Embedding model: `BAAI/bge-m3:int8@4de1325`
- Reranker (hybrid mode): `BAAI/bge-reranker-v2-m3:int8@6f5ff65`, top 20 fused results
- Corpus: 28 documents, 152 chunks (target 1800 / max 2400 characters, overlap 200)
- Questions: 108 (95 answerable)
- Hybrid: RRF k = 60, 30 candidates per method; top k = 10

A result counts as relevant when it comes from the labelled document and contains one of the labelled evidence passages. Metrics cover answerable questions only.

## Results

| Mode | Success@1 | Success@5 | Success@10 | MRR@10 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|
| hybrid (RRF) | 91.6% | 100.0% | 100.0% | 0.953 | 4173 ms | 5623 ms |

## By question category (Success@5 / MRR@10)

| Category | Questions | hybrid (RRF) |
|---|---|---|
| cross_lingual | 19 | 100.0% / 0.904 |
| distractor | 6 | 100.0% / 1.000 |
| identifier | 21 | 100.0% / 0.952 |
| injection | 4 | 100.0% / 1.000 |
| lexical | 11 | 100.0% / 1.000 |
| long_document | 15 | 100.0% / 1.000 |
| paraphrase | 16 | 100.0% / 0.927 |
| version | 3 | 100.0% / 0.833 |

## Similarity distributions (hybrid)

For calibrating a minimum-evidence threshold before answering (Phase 4).

- First relevant chunk of answerable questions: min 0.365 · p25 0.599 · median 0.652 · max 0.793
- Best chunk for unanswerable questions: min 0.383 · p25 0.413 · median 0.441 · max 0.622

Reranker scores (hybrid):

- First relevant chunk of answerable questions: min 0.001 · p25 0.657 · median 0.914 · max 0.999
- Best chunk for unanswerable questions: min 0.000 · p25 0.000 · median 0.002 · max 0.973

## Misses (no relevant chunk in the top 10)

None.

## Caveats

The corpus and questions are synthetic and were written by the same author, which can make questions closer to the wording of their documents than real queries. Cross-lingual questions and topically overlapping distractor documents reduce, but do not remove, this bias. Compare runs with each other rather than reading absolute numbers as production quality.
