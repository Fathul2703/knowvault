# ADR 0008: Full-text search for natural-language questions

- Status: Accepted
- Date: 2026-10-03
- Amends: ADR 0006 (query parsing and full-text ranking)

## Context

The retrieval baseline (ADR 0007) showed full-text search matching none of 54 natural-language
questions: `websearch_to_tsquery` joins words with AND and the `simple` configuration keeps
function words, so every word of "How long are support conversations kept?" had to appear in the
chunk. Hybrid search therefore equalled vector search for questions.

## Options measured

Each variant was run with `make eval-docker` on the same corpus, questions and model
(bge-m3 int8); reports are in `eval/reports/`.

| Variant | Full text S@1 | Full text MRR | Hybrid S@1 | Hybrid MRR | Report |
|---|---|---|---|---|---|
| Baseline: AND of all words | 0.0% | 0.000 | 92.6% | 0.963 | `…1821-retrieval-baseline` |
| A: stop words removed, OR, ranked by `ts_rank_cd` | 57.4% | 0.623 | **63.0%** | **0.751** | `…1835-…-fulltext-or-rank` |
| B: as A, ranked by words matched, then `ts_rank_cd` | 61.1% | 0.639 | **63.0%** | **0.739** | `…1837-…-fulltext-or-coverage` |
| C: as B, plus minimum match of half the words | 50.0% | 0.500 | 92.6% | 0.963 | `…1838-…-fulltext-min-match` |

Vector search scored 92.6% / 0.963 in every run.

A and B made full-text search useful on its own but **damaged hybrid search**: for cross-lingual
questions (hybrid MRR 0.43 and 0.39), keyword matches on one incidental shared word put a
distractor document in both lists, and RRF ranked it above the correct document that only the
vector list contained.

## Decision

Variant C:

- Queries with web-search syntax (`"phrase"`, `-word`, `OR`) are passed to
  `websearch_to_tsquery` unchanged, as before.
- Other queries are natural questions: surrounding punctuation is removed, common English and
  Indonesian function words are dropped, and the remaining words (at most 16, kept whole so that
  PostgreSQL tokenises them like the index) are joined with OR.
- A chunk must contain at least half of those words, rounded up ("minimum should match").
- Chunks are ranked by the number of distinct query words they contain (coordination level
  matching), then by `ts_rank_cd`. The full-text score reported by the API is that sum.

## Consequences

- Full-text mode now answers half of the natural questions, all identifier questions and most
  lexical ones, with high precision: when it finds an answer it is almost always ranked first.
- Hybrid search is no worse than vector search on this corpus — and, on this corpus, not better
  either, because vector search already finds the answer in the top 5 for every question. The
  benefit of hybrid search for exact tokens (`ERR_4711` versus `ERR_4712`, ADR 0006) is not yet
  covered by enough questions to show in the numbers; adding such questions is a useful next
  step for the dataset.
- The 50% threshold and the stop-word lists are simple, general rules, deliberately not tuned
  further on a 54-question synthetic dataset to avoid overfitting it.
- Without stemming, a question word must appear in the same form ("mean" does not match
  "means").
