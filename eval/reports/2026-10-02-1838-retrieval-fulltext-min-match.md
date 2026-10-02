# Retrieval evaluation — 2026-10-02 (fulltext-min-match)

Generated 2026-10-02 18:38 UTC by `knowvault eval-retrieval`.

## Setup

- Embedding model: `BAAI/bge-m3:int8@4de1325`
- Corpus: 16 documents, 81 chunks (target 1800 / max 2400 characters, overlap 200)
- Questions: 62 (54 answerable)
- Hybrid: RRF k = 60, 30 candidates per method; top k = 10

A result counts as relevant when it comes from the labelled document and contains one of the labelled evidence passages. Metrics cover answerable questions only.

## Results

| Mode | Success@1 | Success@5 | Success@10 | MRR@10 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|
| hybrid (RRF) | 92.6% | 100.0% | 100.0% | 0.963 | 67 ms | 92 ms |
| vector | 92.6% | 100.0% | 100.0% | 0.963 | 70 ms | 119 ms |
| full text | 50.0% | 50.0% | 50.0% | 0.500 | 20 ms | 21 ms |

## By question category (Success@5 / MRR@10)

| Category | Questions | hybrid (RRF) | vector | full text |
|---|---|---|---|---|
| cross_lingual | 19 | 100.0% / 0.947 | 100.0% / 0.947 | 0.0% / 0.000 |
| identifier | 8 | 100.0% / 1.000 | 100.0% / 1.000 | 100.0% / 1.000 |
| lexical | 11 | 100.0% / 1.000 | 100.0% / 1.000 | 81.8% / 0.818 |
| paraphrase | 16 | 100.0% / 0.938 | 100.0% / 0.938 | 62.5% / 0.625 |

## Similarity distributions (hybrid)

For calibrating a minimum-evidence threshold before answering (Phase 4).

- First relevant chunk of answerable questions: min 0.365 · p25 0.572 · median 0.638 · max 0.793
- Best chunk for unanswerable questions: min 0.385 · p25 0.423 · median 0.480 · max 0.568

## Misses (no relevant chunk in the top 10)

### full text: 27 of 54

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

…and 17 more; see the JSON report for all results.


## Caveats

The corpus and questions are synthetic and were written by the same author, which can make questions closer to the wording of their documents than real queries. Cross-lingual questions and topically overlapping distractor documents reduce, but do not remove, this bias. Compare runs with each other rather than reading absolute numbers as production quality.
