# Answer evaluation — 2026-10-03 (fake-llm)

Generated 2026-10-03 14:52 UTC by `knowvault eval-answers`.

## Setup

- Answer model: `fake-extractive` (provider `fake`), prompt `answer-v1`
- Embedding model: `BAAI/bge-m3:int8@4de1325`
- Corpus: 23 documents, 109 chunks
- Questions: 81 (71 answerable, 10 unanswerable; 4 about documents that contain a prompt-injection attempt)
- Up to 8 sources and 24,000 characters per answer, at most 1024 output tokens

> **Pipeline check, not answer quality.** The fake model quotes the first sentence of the sources that share words with the question. These numbers show that the evaluation and the answer pipeline work; run with `LLM_PROVIDER=anthropic` to measure a language model.

Each question is asked in a new conversation. A source *contains the evidence* when it comes from the labelled document and includes a labelled evidence passage — the same rule as the retrieval evaluation.

## Results

| Measure | Value |
|---|---|
| Answerable questions answered | 90.1% (64/71) |
| Answerable questions refused | 9.9% (7/71) |
| Unanswerable questions refused | 10.0% (1/10) |
| Unanswerable questions answered anyway | 90.0% (9/10) |
| **Refusal accuracy** (right decision, all questions) | 80.2% |
| Errors | 0.0% (0/81) |
| Answers citing at least one source | 100.0% (73/73) |
| **Answers with invalid citation numbers** | 0.0% (0/73) |
| Answers citing a source that contains the evidence | 73.4% (47/64) |
| Evidence among the sources given (retrieval) | 100.0% (71/71) |
| **Prompt-injection leaks** | 0 of 4 |
| Latency p50 / p95 | 82 ms / 137 ms |
| Tokens: input / output (per answered question) | 80,554 / 3,156 (1,103 / 43) |

## By category

| Category | Questions | Answered | Refused | Cites the evidence |
|---|---|---|---|---|
| cross_lingual | 19 | 73.7% | 26.3% | 21.4% |
| identifier | 21 | 90.5% | 9.5% | 84.2% |
| injection | 4 | 100.0% | 0.0% | 75.0% |
| lexical | 11 | 100.0% | 0.0% | 100.0% |
| paraphrase | 16 | 100.0% | 0.0% | 87.5% |
| unanswerable | 10 | 90.0% | 10.0% | — |

## Problems

### Refused although answerable (7)

| Question | Category | Evidence among sources |
|---|---|---|
| Apa yang terjadi pada klien yang mengabaikan batas permintaan dan terus mengirim? | cross_lingual | yes |
| Apakah minuman beralkohol diganti saat perjalanan dinas? | cross_lingual | yes |
| What should I do if my account might be compromised? | cross_lingual | yes |
| How much water does alternate wetting and drying save in rice fields? | cross_lingual | yes |
| When can hydroponic lettuce be harvested? | cross_lingual | yes |
| What did 2.3.12 add? | identifier | yes |
| Apakah versi 3.2.4 wajib dipasang? | identifier | yes |

### Answered although unanswerable (9)

| Question | Answer |
|---|---|
| What is the company's policy on bringing pets to the office? | According to your documents: This policy says how long the company keeps each kind of data and how it is deleted. [1] Employees may travel for customer visits,… |
| Berapa gaji minimum untuk posisi engineer junior? | According to your documents: Request access to the code repository, the issue tracker and the chat workspace through the access portal. [3] |
| How do I configure single sign-on with SAML? | According to your documents: You receive a laptop with the operating system already installed. [6] |
| What does error ERR_9999 mean? | According to your documents: The importer writes a single error code to the job log when it stops. [1] The billing service charges customers' saved payment meth… |
| Kapan kantor cabang Surabaya dibuka? | According to your documents: Daftar ini berisi alat tulis yang disediakan untuk semua kantor cabang. [1] SKU-A1207 adalah kertas HVS ukuran A4 80 gram, satu rim… |
| Which database engine does the ledger app use? | According to your documents: This runbook covers the nightly importer that loads partner invoices into the ledger. [4] |
| Berapa lama masa garansi laptop karyawan? | According to your documents: Setiap karyawan tetap mendapat 14 hari cuti tahunan. [2] You receive a laptop with the operating system already installed. [1] |
| How many parking spaces does the head office have? | According to your documents: The free plan allows 60 requests per minute and 10,000 requests per day. [7] |
| Siapa nama direktur keuangan perusahaan? | According to your documents: Tim teknik menyampaikan risiko bahwa migrasi basis data dapat mengganggu laporan keuangan selama satu akhir pekan. [3] Semua karyaw… |

### Answers not citing the evidence (17)

| Question | Category | Evidence among sources | Answer |
|---|---|---|---|
| Apa yang harus dilakukan jika partner mengirim berkas dengan kolom yang tidak dikenal? | cross_lingual | yes | According to your documents: Semua karyawan wajib memakai pengelola kata sandi yang disediakan perusahaan. [3] This runbook covers the nightly importer that loa… |
| How much did cup scores improve with fermentation in sealed tanks? | paraphrase | yes | According to your documents: The sealed tanks added about eight percent to processing costs, mostly for the tanks themselves and for extra labour during sealing… |
| Apa yang menyebabkan rasa cuka pada kopi dalam percobaan itu? | cross_lingual | yes | According to your documents: Petak percobaan diairi hanya ketika permukaan air turun sampai lima belas sentimeter di bawah permukaan tanah, diukur dengan pipa p… |
| What security issue was fixed in 2.3.2? | identifier | yes | According to your documents: Request access to the code repository, the issue tracker and the chat workspace through the access portal. [4] Version 2.4.0 adds m… |
| Kapan pengingat untuk faktur yang belum dibayar dikirim? | cross_lingual | yes | According to your documents: Tim penjualan akan mewawancarai dua puluh pelanggan tentang kebutuhan faktur berulang sebelum akhir bulan. [6] |
| Berapa suhu oven untuk memanggang roti sourdough? | cross_lingual | yes | According to your documents: These are notes from a year of baking sourdough bread at home. [1] Sayuran daun memerlukan sinar matahari langsung minimal lima jam… |
| Do I need a doctor's note for one day of sick leave? | cross_lingual | yes | According to your documents: Submit expense claims within 30 days after the trip with a photo of every receipt. [6] Travel on a weekend does not create extra le… |
| How long is paternity leave for fathers? | cross_lingual | yes | According to your documents: Travel on a weekend does not create extra leave days. [7] |
| Kalau saya disuruh masuk kerja waktu tanggal merah, dapat apa? | paraphrase | yes | According to your documents: Tiket prioritas tinggi, misalnya pelanggan tidak bisa masuk sama sekali, harus dijawab dalam satu jam kerja. [1] Setiap karyawan te… |
| Why is SMS not recommended for two-factor authentication? | cross_lingual | yes | According to your documents: Version 3.2.4 is required for all users from the first of next month, because older versions use an authentication method that the… |

…and 7 more; see the JSON report.

## Manual review

No review sheet was written for this run.

## Caveats

The corpus and questions are synthetic and written by the same author. Automatic measures check decisions and citation numbers, and whether a cited source contains the labelled evidence; they do not check that the source supports each sentence. That is what the manual review is for.
