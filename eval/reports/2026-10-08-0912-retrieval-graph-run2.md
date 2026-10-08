# Retrieval evaluation — 2026-10-08 (graph-run2)

Generated 2026-10-08 09:12 UTC by `knowvault eval-retrieval`.

## Setup

- Embedding model: `BAAI/bge-m3:int8@4de1325`
- Reranker: none
- Corpus: 31 documents, 167 chunks (target 1000 / max 1400 characters, overlap 150)
- Questions: 124 (111 answerable)
- Hybrid: RRF k = 60, 30 candidates per method; top k = 10
- Graph retrieval: chunks of entities named in the question as a third RRF list — `none` contributed to the results of 0 of 124 questions; `entities` contributed to the results of 31 of 124 questions; `neighbours` contributed to the results of 31 of 124 questions

A result counts as relevant when it comes from the labelled document and contains one of the labelled evidence passages. Metrics cover answerable questions only.

## Results

| Mode | Success@1 | Success@5 | Success@10 | MRR@10 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|
| hybrid (RRF) | 84.7% | 100.0% | 100.0% | 0.919 | 53 ms | 61 ms |
| vector | 86.5% | 100.0% | 100.0% | 0.929 | 51 ms | 68 ms |
| full text | 46.8% | 49.5% | 49.5% | 0.480 | 26 ms | 31 ms |
| hybrid, no graph | 84.7% | 100.0% | 100.0% | 0.919 | 62 ms | 117 ms |
| hybrid + graph (entities) | 82.9% | 100.0% | 100.0% | 0.908 | 59 ms | 72 ms |
| hybrid + graph (neighbours) | 82.9% | 100.0% | 100.0% | 0.908 | 61 ms | 80 ms |

## By question category (Success@5 / MRR@10)

| Category | Questions | hybrid (RRF) | vector | full text | hybrid, no graph | hybrid + graph (entities) | hybrid + graph (neighbours) |
|---|---|---|---|---|---|---|---|
| cross_lingual | 19 | 100.0% / 0.807 | 100.0% / 0.833 | 0.0% / 0.000 | 100.0% / 0.807 | 100.0% / 0.781 | 100.0% / 0.781 |
| distractor | 6 | 100.0% / 0.917 | 100.0% / 0.917 | 16.7% / 0.167 | 100.0% / 0.917 | 100.0% / 0.764 | 100.0% / 0.783 |
| identifier | 21 | 100.0% / 0.976 | 100.0% / 0.893 | 81.0% / 0.778 | 100.0% / 0.976 | 100.0% / 1.000 | 100.0% / 1.000 |
| injection | 4 | 100.0% / 1.000 | 100.0% / 1.000 | 50.0% / 0.375 | 100.0% / 1.000 | 100.0% / 1.000 | 100.0% / 1.000 |
| lexical | 11 | 100.0% / 1.000 | 100.0% / 1.000 | 81.8% / 0.818 | 100.0% / 1.000 | 100.0% / 1.000 | 100.0% / 1.000 |
| long_document | 15 | 100.0% / 0.933 | 100.0% / 1.000 | 40.0% / 0.400 | 100.0% / 0.933 | 100.0% / 0.933 | 100.0% / 0.933 |
| paraphrase | 16 | 100.0% / 0.906 | 100.0% / 0.875 | 62.5% / 0.625 | 100.0% / 0.906 | 100.0% / 0.906 | 100.0% / 0.906 |
| unstructured | 16 | 100.0% / 0.887 | 100.0% / 1.000 | 50.0% / 0.469 | 100.0% / 0.887 | 100.0% / 0.865 | 100.0% / 0.859 |
| version | 3 | 100.0% / 1.000 | 100.0% / 1.000 | 66.7% / 0.667 | 100.0% / 1.000 | 100.0% / 1.000 | 100.0% / 1.000 |

## Similarity distributions (hybrid)

For calibrating a minimum-evidence threshold before answering (Phase 4).

- First relevant chunk of answerable questions: min 0.371 · p25 0.595 · median 0.646 · max 0.786
- Best chunk for unanswerable questions: min 0.351 · p25 0.451 · median 0.495 · max 0.613

## Misses (no relevant chunk in the top 10)

### full text: 56 of 111

| Question | Category | Expected | Top results |
|---|---|---|---|
| Berapa kali importer mencoba ulang sebelum menyerah? | cross_lingual | incident-runbook.md | — |
| When do I need to involve the team lead during an outage? | paraphrase | incident-runbook.md | — |
| Apa yang harus dilakukan jika partner mengirim berkas dengan kolom yang tidak dikenal? | cross_lingual | incident-runbook.md | — |
| Does removing a record also erase it from the nightly copies? | paraphrase | data-retention-policy.md | — |
| Berapa lama permintaan penghapusan data pribadi harus diselesaikan? | cross_lingual | data-retention-policy.md | — |
| How often are the encryption keys of backups changed? | paraphrase | data-retention-policy.md | — |
| Berapa banyak kunci keamanan perangkat keras yang diberikan kepada setiap engineer? | cross_lingual | engineer-onboarding.md | — |
| What is the recommended size of a pull request? | lexical | engineer-onboarding.md | — |
| Apa yang terjadi pada klien yang mengabaikan batas permintaan dan terus mengirim? | cross_lingual | api-rate-limits.md | — |
| How much did cup scores improve with fermentation in sealed tanks? | paraphrase | coffee-fermentation-study.md | — |

…and 46 more; see the JSON report for all results.


## Caveats

The corpus and questions are synthetic and were written by the same author, which can make questions closer to the wording of their documents than real queries. Cross-lingual questions and topically overlapping distractor documents reduce, but do not remove, this bias. Compare runs with each other rather than reading absolute numbers as production quality.
