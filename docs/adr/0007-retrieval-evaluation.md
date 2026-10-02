# ADR 0007: Retrieval evaluation harness

- Status: Accepted
- Date: 2026-10-03

## Context

Phase 3 ships vector, full-text and hybrid search (ADR 0005, 0006), but their quality had only
been checked with a handful of manual queries. `docs/ARCHITECTURE.md` §10.4 asks for a
repeatable evaluation labelled by evidence text rather than chunk ids, so that later changes
(chunking, stemming, fusion parameters, reranking) can be compared.

## Decision

- **Synthetic, self-written corpus.** 16 Markdown documents (8 English, 8 Indonesian) about a
  fictional company, with deliberately overlapping topics as distractors. A public corpus would
  require committing dozens of verbatim passages of third-party text as labels; a written corpus
  avoids licensing and attribution issues. The bias of one author writing documents and
  questions is stated in every report.
- **62 questions** in five categories — lexical, paraphrase, cross-lingual, identifier and
  unanswerable — each labelled with its document and short evidence passages.
- **Relevance:** a chunk is relevant when it comes from the labelled document and contains an
  evidence passage (case and whitespace ignored). A unit test runs the production parser,
  normaliser and chunker over the corpus and fails if any evidence passage is no longer inside
  one chunk.
- **Production code paths:** `knowvault eval-retrieval` creates a disposable `*_eval` database,
  uploads the corpus through the library service, processes it with the worker pipeline and
  searches with the search service, so the evaluation measures what users get.
- **Metrics:** Success@1/5/10 (share of answerable questions with a relevant chunk in the top k),
  MRR@10, latency p50/p95 — per mode and per category — plus the similarity of the first relevant
  chunk versus the best chunk for unanswerable questions.
- **Reports** (Markdown + JSON, dated) are committed to `eval/reports/`. CI runs the dataset and
  runner tests with fake embeddings; the real evaluation runs on demand (`make eval-docker`).

## Findings of the baseline (2026-10-02, bge-m3 int8)

| Mode | Success@1 | Success@5 | MRR@10 |
|---|---|---|---|
| hybrid | 92.6% | 100% | 0.963 |
| vector | 92.6% | 100% | 0.963 |
| full text | 0% | 0% | 0.000 |

1. **Full-text search never matches natural-language questions.** `websearch_to_tsquery`
   joins words with AND and the `simple` configuration keeps every word, so "How long are
   support conversations kept?" requires "how", "long" and "are" in the chunk. Hybrid search
   therefore equals vector search for questions; it only helps keyword-style queries such as
   `ERR_4711`. Addressed in ADR 0008.
2. **Vector search is strong on this corpus**, including all cross-lingual questions in the
   top 5. The synthetic corpus is probably easier than real data.
3. **Similarity does not separate answerable from unanswerable questions**: relevant chunks
   score as low as 0.365, while the best chunk for unanswerable questions reaches 0.568. A
   similarity threshold alone would reject many answerable questions, which supports not using
   it as the only evidence gate in Phase 4 (ARCHITECTURE §10.2).
4. Writing the corpus surfaced a normaliser limitation: a hyphenated word wrapped at the end of a
   line ("terus-⏎menerus") is joined into one word ("terusmenerus"), because the rule meant for
   hyphenation in PDFs cannot tell it apart from Indonesian reduplication.

## Consequences

- Retrieval changes can be judged by comparing reports; regressions show up per category.
- The corpus is small (81 chunks); latency numbers do not predict large libraries.
- Questions written by the corpus author make absolute scores optimistic.
