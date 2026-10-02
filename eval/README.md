# Retrieval evaluation

Measures how well KnowVault finds the passage that answers a question, so changes to chunking,
embeddings or search can be compared with numbers instead of impressions.

```bash
make eval-docker   # in the Compose stack, using the downloaded bge-m3 model
make eval          # on your machine (downloads the model into EMBEDDING_CACHE_DIR if needed)
```

Each run creates a fresh database named `<DATABASE_URL database>_eval` (or `EVAL_DATABASE_URL`;
the name must end in `_eval`), uploads the corpus through the normal library and worker code
(parse → chunk → embed), searches every question in the hybrid, vector and full-text modes,
drops the database, and writes a dated report to `reports/` (Markdown for reading, JSON with
every result). Commit the report together with the change it measures.

## Contents

| Path | What |
|---|---|
| `corpus/` | 16 short Markdown documents, 8 in English and 8 in Indonesian |
| `datasets/retrieval.jsonl` | 62 questions: 54 answerable, 8 that the corpus cannot answer |
| `reports/` | One Markdown and one JSON report per run |

Each question line has an `id`, the `question`, its `language`, a `category`
(`lexical`, `paraphrase`, `cross_lingual`, `identifier`, `unanswerable`), the corpus file
(`document`) that answers it and one or more short `evidence` passages copied from that file.
A retrieved chunk is relevant when it comes from that file and contains an evidence passage
(case and whitespace are ignored). Labels do not refer to chunk ids, so they survive changes to
chunking; a unit test checks that every evidence passage still falls inside a single chunk.

## The corpus is synthetic

The documents describe a fictional company and fictional research. They were written for this
repository (and are covered by its licence) so that evidence passages can be committed without
copying third-party text. Topics deliberately overlap — similar error codes, two documents
about backups, two recipes, two research summaries — so that wrong documents compete with the
right one.

Because the same author wrote documents and questions, questions can be closer to the wording of
their documents than real queries would be. Use the numbers to compare runs with each other,
not as a claim about quality on real data.

## Adding questions

1. Add or edit a document in `corpus/` if needed.
2. Append a line to `datasets/retrieval.jsonl` with a unique id and evidence copied verbatim.
3. Run `make test-api`: the dataset tests reject unknown documents, missing evidence and
   evidence that is split across chunks.
