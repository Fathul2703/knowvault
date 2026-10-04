# ADR 0014: Chunk sizes measured with PDFs — 1,000 characters

- Status: Accepted; amends the chunk sizes of ADR 0004
- Date: 2026-10-04

## Context

ADR 0004 set chunks to a target of 1,800 characters (maximum 2,400, overlap 200) before any
evaluation existed, and the architecture asked for the parameters to be tuned with the eval
(§9.2). The first measurement showed nothing to tune. Every corpus document was well-structured
Markdown with short sections, and the chunker never crosses a heading, so every variant from 600
to 2,800 characters produced the same chunks: about 152, averaging 242 characters.

That is not how most uploads look. PDFs are the most common kind, and `pypdf` returns plain page
text without headings, so chunk size and overlap alone decide what a chunk contains.

## Decision

- **Three PDFs join the evaluation corpus** (`unstructured`, 16 questions): a services contract,
  an annual report and a field study, without headings, built deterministically from plain-text
  sources (`eval/corpus-src/`, `eval/tools/build_pdf_corpus.py`; a test checks that the
  committed PDFs match them).
- **Chunk sizes are settings** (`CHUNK_TARGET_CHARS`, `CHUNK_MAX_CHARS`, `CHUNK_OVERLAP_CHARS`),
  validated so that overlap < target ≤ maximum.
- **The default becomes 1,000 / 1,400 / 150.** Existing documents keep their chunks until
  reprocessed; `knowvault reindex --all` re-chunks them.

## Measurements

31 documents, 111 answerable questions, bge-m3. The evaluation counts as a miss any evidence
passage that a variant splits across chunks; only the largest variant splits one.

| Target / max / overlap | Chunks | Hybrid S@1 | Hybrid MRR@10 | Vector MRR@10 | PDF questions: hybrid MRR / S@5 |
|---|---|---|---|---|---|
| 600 / 900 / 100 | 178 | 86.5% | 0.924 | 0.932 | 0.877 / 100% |
| **1,000 / 1,400 / 150** | 167 | 85.6% | 0.920 | 0.930 | 0.887 / 100% |
| 1,800 / 2,400 / 200 (before) | 159 | 82.9% | 0.902 | 0.900 | 0.870 / 93.8% |
| 1,800 / 2,400 / 0 | 159 | 83.8% | 0.909 | 0.906 | 0.875 / 93.8% |
| 2,800 / 3,600 / 250 | 158 | 82.0% | 0.896 | 0.885 | 0.786 / 93.8% |

Reports: `eval/reports/2026-10-04-075*-retrieval-chunks-*.md`.

- **Large PDF chunks act as hubs.** A 1,700-character chunk of the contract or the annual report
  mentions so many facts that it outranks the right passage of other documents: support
  response times, the water saved by alternate wetting and drying, the timing of performance
  reviews. Smaller chunks remove most of these false winners and also bring the contract's
  audit and data-deletion clauses to the top.
- **They are not free.** The contract's 45-day payment term drops from rank 1 to rank 5 once its
  chunk is small enough to compete with the vendor policy's 30 days. Overlap matters little at
  this size: 0 and 200 differ by one question.
- **600 and 1,000 are within one question of each other.** 1,000 is chosen because it changes
  fewer results for the worse (6 better and 2 worse, against 8 better and 3 worse for 600). It also
  gives each cited passage more surrounding text, which answers from PDFs need.
- **Answers (fake model):** the evidence reaches the model for 111 of 111 questions with both
  1,800 and 1,000; refusal accuracy is 83.9% and 83.1%, and the answers citing the evidence
  are 69.3% and 68.0%. Input tokens fall by 7%
  ([1,800](../../eval/reports/2026-10-04-0758-answers-chunks-1800-fake-llm.md),
  [1,000](../../eval/reports/2026-10-04-0800-answers-chunks-1000-fake-llm.md)). Whether smaller
  passages change how well Claude answers is still to be measured.

## Consequences

- Retrieval on unstructured documents improves and no longer degrades results for structured
  ones. Markdown and Word documents with headings are unaffected unless a section is longer
  than 1,000 characters.
- Libraries hold about 5–10% more chunks; embedding time grows accordingly.
- Deployments that want the new chunks for existing documents run `knowvault reindex --all`.
