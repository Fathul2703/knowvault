# Retrieval evaluation — 2026-10-02 (fulltext-or-coverage)

Generated 2026-10-02 18:37 UTC by `knowvault eval-retrieval`.

## Setup

- Embedding model: `BAAI/bge-m3:int8@4de1325`
- Corpus: 16 documents, 81 chunks (target 1800 / max 2400 characters, overlap 200)
- Questions: 62 (54 answerable)
- Hybrid: RRF k = 60, 30 candidates per method; top k = 10

A result counts as relevant when it comes from the labelled document and contains one of the labelled evidence passages. Metrics cover answerable questions only.

## Results

| Mode | Success@1 | Success@5 | Success@10 | MRR@10 | Latency p50 | Latency p95 |
|---|---|---|---|---|---|---|
| hybrid (RRF) | 63.0% | 94.4% | 98.1% | 0.739 | 67 ms | 92 ms |
| vector | 92.6% | 100.0% | 100.0% | 0.963 | 64 ms | 80 ms |
| full text | 61.1% | 68.5% | 70.4% | 0.639 | 20 ms | 21 ms |

## By question category (Success@5 / MRR@10)

| Category | Questions | hybrid (RRF) | vector | full text |
|---|---|---|---|---|
| cross_lingual | 19 | 89.5% / 0.391 | 100.0% / 0.947 | 15.8% / 0.112 |
| identifier | 8 | 100.0% / 1.000 | 100.0% / 1.000 | 100.0% / 1.000 |
| lexical | 11 | 100.0% / 0.955 | 100.0% / 1.000 | 100.0% / 0.927 |
| paraphrase | 16 | 93.8% / 0.872 | 100.0% / 0.938 | 93.8% / 0.887 |

## Similarity distributions (hybrid)

For calibrating a minimum-evidence threshold before answering (Phase 4).

- First relevant chunk of answerable questions: min 0.365 · p25 0.572 · median 0.638 · max 0.793
- Best chunk for unanswerable questions: min 0.366 · p25 0.381 · median 0.417 · max 0.559

## Misses (no relevant chunk in the top 10)

### hybrid (RRF): 1 of 54

| Question | Category | Expected | Top results |
|---|---|---|---|
| Do I need a doctor's note for one day of sick leave? | cross_lingual | kebijakan-cuti.md | travel-expense-policy.md, travel-expense-policy.md, data-retention-policy.md |

### full text: 16 of 54

| Question | Category | Expected | Top results |
|---|---|---|---|
| Berapa banyak kunci keamanan perangkat keras yang diberikan kepada setiap engineer? | cross_lingual | engineer-onboarding.md | pemulihan-bencana.md, keamanan-kata-sandi.md, keamanan-kata-sandi.md |
| Apa yang terjadi pada klien yang mengabaikan batas permintaan dan terus mengirim? | cross_lingual | api-rate-limits.md | riset-irigasi-sawah.md, riset-irigasi-sawah.md, pemulihan-bencana.md |
| Apa yang menyebabkan rasa cuka pada kopi dalam percobaan itu? | cross_lingual | coffee-fermentation-study.md | riset-irigasi-sawah.md |
| Apakah minuman beralkohol diganti saat perjalanan dinas? | cross_lingual | travel-expense-policy.md | keamanan-kata-sandi.md, hidroponik.md |
| Kapan pengingat untuk faktur yang belum dibayar dikirim? | cross_lingual | release-notes.md | keamanan-kata-sandi.md, rapat-perencanaan-q3.md, rapat-perencanaan-q3.md |
| Berapa suhu oven untuk memanggang roti sourdough? | cross_lingual | sourdough-notes.md | resep-rendang.md, hidroponik.md, sourdough-notes.md |
| Do I need a doctor's note for one day of sick leave? | cross_lingual | kebijakan-cuti.md | travel-expense-policy.md, engineer-onboarding.md, data-retention-policy.md |
| How long is paternity leave for fathers? | cross_lingual | kebijakan-cuti.md | travel-expense-policy.md, data-retention-policy.md, api-rate-limits.md |
| Kalau saya disuruh masuk kerja waktu tanggal merah, dapat apa? | paraphrase | kebijakan-cuti.md | helpdesk-tiket.md, kebijakan-cuti.md, keamanan-kata-sandi.md |
| What should I do if my account might be compromised? | cross_lingual | keamanan-kata-sandi.md | api-rate-limits.md |

…and 6 more; see the JSON report for all results.


## Caveats

The corpus and questions are synthetic and were written by the same author, which can make questions closer to the wording of their documents than real queries. Cross-lingual questions and topically overlapping distractor documents reduce, but do not remove, this bias. Compare runs with each other rather than reading absolute numbers as production quality.
