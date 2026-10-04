# Evaluation

Two evaluations share one labelled corpus and question set, so changes can be compared with
numbers instead of impressions:

- **Retrieval** — how well KnowVault finds the passage that answers a question (chunking,
  embeddings, search).
- **Answers** — whether answers are given or refused when they should be, whether citations
  point at the right passages, and whether instructions planted in documents leak into
  answers (prompt, model, context assembly).

## Retrieval evaluation

```bash
make eval-docker   # in the Compose stack, using the downloaded bge-m3 model
make eval          # on your machine (downloads the model into EMBEDDING_CACHE_DIR if needed)
```

Each run creates a fresh database named `<DATABASE_URL database>_eval` (or `EVAL_DATABASE_URL`;
the name must end in `_eval`), uploads the corpus through the normal library and worker code
(parse → chunk → embed), searches every question in the hybrid, vector and full-text modes,
drops the database, and writes a dated report to `reports/` (Markdown for reading, JSON with
every result). Commit the report together with the change it measures.

### Reranking (retrieval)

`RERANKER=bge-reranker-v2-m3` (with `--modes hybrid` to save time) evaluates hybrid search with
the cross-encoder; the report then also shows the distribution of reranker scores for answerable
and unanswerable questions. The measurements behind keeping it off are in ADR 0013.

## Contents

| Path | What |
|---|---|
| `corpus/` | 28 Markdown documents, 14 in English and 14 in Indonesian, two of them long |
| `datasets/retrieval.jsonl` | 108 questions: 95 answerable, 13 that the corpus cannot answer |
| `reports/` | One Markdown and one JSON report per run of either evaluation |
| `reviews/` | Manual review sheets of answer evaluation runs, once filled in |

Each question line has an `id`, the `question`, its `language`, a `category`
(`lexical`, `paraphrase`, `cross_lingual`, `identifier`, `injection`, `version`, `distractor`,
`long_document`, `unanswerable`), the corpus file
(`document`) that answers it and one or more short `evidence` passages copied from that file.
A retrieved chunk is relevant when it comes from that file and contains an evidence passage
(case and whitespace are ignored). Labels do not refer to chunk ids, so they survive changes to
chunking; a unit test checks that every evidence passage still falls inside a single chunk.

## The corpus is synthetic

The documents describe a fictional company and fictional research. They were written for this
repository (and are covered by its licence) so that evidence passages can be committed without
copying third-party text. Topics deliberately overlap — similar error codes, two documents
about backups, two recipes, two research summaries — so that wrong documents compete with the
right one. Identifiers also come in near-duplicates that differ only in the order of their
characters (`ERR_4713` / `ERR_4171` / `ERR_7411`, `SKU-A1270` / `SKU-A1207`, version `2.4.1` /
`2.3.12`), which embeddings tend to confuse and exact-word search does not.

Because the same author wrote documents and questions, questions can be closer to the wording of
their documents than real queries would be. Use the numbers to compare runs with each other,
not as a claim about quality on real data.

Some documents are there to make retrieval harder, as real libraries do:

- `version`: an archived version of the leave policy (`kebijakan-cuti-2022.md`) with other
  numbers than the current one. Questions about the current rules must not be answered from it.
- `distractor`: neighbours on the same topic with other facts — the partner API's limits next to
  the public API's, and a postmortem of an ERR_4711 outage next to the runbook.
- `long_document`: an employee handbook and a warehouse manual of several thousand words, where
  the answer is one section among many and is often asked with other words or in the other
  language.
- Unanswerable questions include near misses, such as the limit of a plan that does not exist or
  an outage in a month without a postmortem.

Two documents (`vendor-onboarding.md`, `pengumuman-kantin.md`) contain a prompt-injection
attempt among ordinary content. Their questions have the category `injection` and a `canary`:
text that appears in an answer only if the model followed the planted instructions.

## Answer evaluation

```bash
make eval-answers-docker   # in the Compose stack; uses LLM_PROVIDER from .env
make eval-answers          # on your machine
```

Every question is asked in a new conversation through the production answer service
(retrieval, context assembly, prompt, streaming, `NO_ANSWER` detection, citation checks), in a
disposable `*_eval` database as above. The report measures:

| Measure | Meaning |
|---|---|
| Answered / refused | For answerable questions an answer is right; for unanswerable ones a refusal is |
| Refusal accuracy | Right decisions over all questions (errors count as wrong) |
| Invalid citation numbers | Answers citing `[n]` for a source they were not given |
| Cites the evidence | Answers citing a source that contains the labelled evidence passage |
| Evidence among the sources | Retrieval gave the model the evidence at all (an upper bound for answering) |
| Prompt-injection leaks | Answers (or streamed text) containing an injection question's canary |
| Latency, tokens | Per run and per answered question |

With `LLM_PROVIDER=fake` (the default) the run checks the pipeline only: the fake model quotes
sentences that share words with the question, so it answers almost everything. Its report is a
floor that a language model must beat. To measure Claude, set `LLM_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY`; `--limit N` asks only the first N questions to try it cheaply.

### Manual review

Automatic measures cannot tell whether a cited passage really supports the sentence citing it.
With `--review-dir` (set by the make targets) the run also writes `reviews/<run>-review.md`:
30 answers sampled reproducibly, each with its cited passages and boxes to tick (`supports`,
`partly`, `does not support` per citation; `faithful`, `partly faithful`, `unfaithful` per
answer). Fill it in, then:

```bash
cd apps/api && uv run knowvault eval-review ../../eval/reviews/<run>-review.md
```

prints the totals and lists sections left unmarked. Commit the filled sheet with its report.

## Adding questions

1. Add or edit a document in `corpus/` if needed.
2. Append a line to `datasets/retrieval.jsonl` with a unique id and evidence copied verbatim.
3. Run `make test-api`: the dataset tests reject unknown documents, missing evidence and
   evidence that is split across chunks.
