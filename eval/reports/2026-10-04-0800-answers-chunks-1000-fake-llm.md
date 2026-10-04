# Answer evaluation — 2026-10-04 (chunks-1000-fake-llm)

Generated 2026-10-04 08:00 UTC by `knowvault eval-answers`.

## Setup

- Answer model: `fake-extractive` (provider `fake`), prompt `answer-v1`
- Embedding model: `BAAI/bge-m3:int8@4de1325`; reranker: `none`
- Corpus: 31 documents, 167 chunks
- Questions: 124 (111 answerable, 13 unanswerable; 4 about documents that contain a prompt-injection attempt)
- Up to 8 sources and 24,000 characters per answer, at most 1024 output tokens

> **Pipeline check, not answer quality.** The fake model quotes the first sentence of the sources that share words with the question. These numbers show that the evaluation and the answer pipeline work; run with `LLM_PROVIDER=anthropic` to measure a language model.

Each question is asked in a new conversation. A source *contains the evidence* when it comes from the labelled document and includes a labelled evidence passage — the same rule as the retrieval evaluation.

## Results

| Measure | Value |
|---|---|
| Answerable questions answered | 90.1% (100/111) |
| Answerable questions refused | 9.9% (11/111) |
| Unanswerable questions refused | 23.1% (3/13) |
| Unanswerable questions answered anyway | 76.9% (10/13) |
| **Refusal accuracy** (right decision, all questions) | 83.1% |
| Errors | 0.0% (0/124) |
| Answers citing at least one source | 100.0% (110/110) |
| **Answers with invalid citation numbers** | 0.0% (0/110) |
| Answers citing a source that contains the evidence | 68.0% (68/100) |
| Evidence among the sources given (retrieval) | 100.0% (111/111) |
| **Prompt-injection leaks** | 0 of 4 |
| Latency p50 / p95 | 82 ms / 105 ms |
| Tokens: input / output (per answered question) | 152,189 / 5,093 (1,383 / 46) |

## By category

| Category | Questions | Answered | Refused | Cites the evidence |
|---|---|---|---|---|
| cross_lingual | 19 | 73.7% | 26.3% | 7.1% |
| distractor | 6 | 100.0% | 0.0% | 50.0% |
| identifier | 21 | 90.5% | 9.5% | 78.9% |
| injection | 4 | 100.0% | 0.0% | 75.0% |
| lexical | 11 | 100.0% | 0.0% | 100.0% |
| long_document | 15 | 86.7% | 13.3% | 69.2% |
| paraphrase | 16 | 100.0% | 0.0% | 87.5% |
| unanswerable | 13 | 76.9% | 23.1% | — |
| unstructured | 16 | 87.5% | 12.5% | 71.4% |
| version | 3 | 100.0% | 0.0% | 66.7% |

## Problems

### Refused although answerable (11)

| Question | Category | Evidence among sources |
|---|---|---|
| Apa yang terjadi pada klien yang mengabaikan batas permintaan dan terus mengirim? | cross_lingual | yes |
| What should I do if my account might be compromised? | cross_lingual | yes |
| What is the target load time for the financial reports page? | cross_lingual | yes |
| How much water does alternate wetting and drying save in rice fields? | cross_lingual | yes |
| When can hydroponic lettuce be harvested? | cross_lingual | yes |
| What did 2.3.12 add? | identifier | yes |
| Apakah versi 3.2.4 wajib dipasang? | identifier | yes |
| Berapa lama masa pemberitahuan kalau saya mengundurkan diri setelah masa percobaan? | long_document | yes |
| How far in advance must a supplier's truck reserve an unloading slot? | long_document | yes |
| Since when has the new warehouse been operating? | unstructured | yes |

…and 1 more; see the JSON report.

### Answered although unanswerable (10)

| Question | Answer |
|---|---|
| What is the company's policy on bringing pets to the office? | According to your documents: This handbook collects the everyday rules of working at the company. [1] Most roles can be done partly from home. [2] |
| Berapa gaji minimum untuk posisi engineer junior? | According to your documents: Request access to the code repository, the issue tracker and the chat workspace through the access portal. [3] |
| What does error ERR_9999 mean? | According to your documents: The importer writes a single error code to the job log when it stops. [1] ERR_7411 means the tax rate for the customer's region is… |
| Kapan kantor cabang Surabaya dibuka? | According to your documents: Daftar ini berisi alat tulis yang disediakan untuk semua kantor cabang. [1] SKU-A1207 adalah kertas HVS ukuran A4 80 gram, satu rim… |
| Which database engine does the ledger app use? | According to your documents: This runbook covers the nightly importer that loads partner invoices into the ledger. [4] |
| Berapa lama masa garansi laptop karyawan? | According to your documents: Setiap karyawan tetap mendapat 14 hari cuti tahunan. [8] You receive a laptop with the operating system already installed. [5] |
| Siapa nama direktur keuangan perusahaan? | According to your documents: Laporan Tahunan 2025 Tahun 2025 adalah tahun pertumbuhan bagi perusahaan. [1] Tingkat retensi pelanggan mencapai 94 persen, dan pel… |
| What is the request limit of the enterprise plan? | According to your documents: This limit does not apply to damage caused intentionally or by gross negligence, to breaches of confidentiality, or to the Customer… |
| Berapa hari cuti tahunan untuk karyawan magang? | According to your documents: Setiap karyawan tetap mendapat 14 hari cuti tahunan. [1] Sisa cuti tahunan yang tidak terpakai boleh dibawa ke tahun berikutnya pal… |
| What was the root cause of the importer outage in January? | According to your documents: At 01:10 the importer started to stop with ERR_4711 for all tenants at once. [2] The storage cluster rejected new connections becau… |

### Answers not citing the evidence (32)

| Question | Category | Evidence among sources | Answer |
|---|---|---|---|
| Berapa kali importer mencoba ulang sebelum menyerah? | cross_lingual | yes | According to your documents: Summary of the incident in which the nightly importer failed for every tenant. [1] At 01:10 the importer started to stop with ERR_4… |
| Apa yang harus dilakukan jika partner mengirim berkas dengan kolom yang tidak dikenal? | cross_lingual | yes | According to your documents: Requests over the limit receive HTTP status 429 with a Retry-After header. [4] A partner can ask the partner manager for a temporar… |
| Berapa banyak kunci keamanan perangkat keras yang diberikan kepada setiap engineer? | cross_lingual | yes | According to your documents: Sepatu keselamatan dan rompi berwarna terang wajib dipakai di seluruh area gudang, juga oleh tamu. [5] Verifikasi dua langkah wajib… |
| How much did cup scores improve with fermentation in sealed tanks? | paraphrase | yes | According to your documents: The sealed tanks added about eight percent to processing costs, mostly for the tanks themselves and for extra labour during sealing… |
| Apa yang menyebabkan rasa cuka pada kopi dalam percobaan itu? | cross_lingual | yes | According to your documents: Petak percobaan diairi hanya ketika permukaan air turun sampai lima belas sentimeter di bawah permukaan tanah, diukur dengan pipa p… |
| Apakah minuman beralkohol diganti saat perjalanan dinas? | cross_lingual | yes | According to your documents: Setiap akhir shift, area kerja dibersihkan dan palet kosong dikembalikan ke tempat palet. [4] |
| What security issue was fixed in 2.3.2? | identifier | yes | According to your documents: Request access to the code repository, the issue tracker and the chat workspace through the access portal. [4] Version 2.4.0 adds m… |
| Kapan pengingat untuk faktur yang belum dibayar dikirim? | cross_lingual | yes | According to your documents: Tim penjualan akan mewawancarai dua puluh pelanggan tentang kebutuhan faktur berulang sebelum akhir bulan. [6] |
| Berapa suhu oven untuk memanggang roti sourdough? | cross_lingual | yes | According to your documents: These are notes from a year of baking sourdough bread at home. [1] Setelah diterima, barang disimpan di lokasi rak yang ditentukan… |
| Do I need a doctor's note for one day of sick leave? | cross_lingual | yes | According to your documents: Register visitors at least one working day in advance in the visitor system, with their full name and the name of their company. [3… |

…and 22 more; see the JSON report.

## Manual review

No review sheet was written for this run.

## Caveats

The corpus and questions are synthetic and written by the same author. Automatic measures check decisions and citation numbers, and whether a cited source contains the labelled evidence; they do not check that the source supports each sentence. That is what the manual review is for.
