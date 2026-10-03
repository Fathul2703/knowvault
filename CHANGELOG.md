# Changelog

All notable changes to KnowVault. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-10-04

The first release: the MVP of docs/ARCHITECTURE.md (Phases 1–4). Upload documents, search them by
meaning and by exact words, and ask questions that are answered only from your documents, with
citations you can open — or refused when the documents do not contain the answer.

### Added

- **Accounts:** invite-only registration, server-side sessions in an HttpOnly cookie, origin
  checks on every state-changing request, Argon2id passwords, admin CLI for invites and
  password resets ([ADR 0002](docs/adr/0002-session-authentication.md)).
- **Library:** collections, Markdown notes, and uploads of PDF, Word, Markdown and text files up
  to 25 MB.
  - A PostgreSQL job queue feeds a worker.
  - Text is extracted in a sandboxed child process with a timeout and a memory limit.
  - Chunks keep their page or heading trail, and failures are explained and can be retried
    ([ADR 0004](docs/adr/0004-document-ingestion.md)).
- **Search:** BAAI/bge-m3 embeddings (int8, multilingual, run locally) in pgvector, PostgreSQL
  full-text search for exact words, and both fused with Reciprocal Rank Fusion. The Search page
  highlights passages and links to the exact chunk
  ([ADR 0005](docs/adr/0005-embeddings-and-vector-search.md),
  [0006](docs/adr/0006-hybrid-search.md), [0008](docs/adr/0008-fulltext-natural-questions.md)).
- **Ask:** conversations with answers streamed as Server-Sent Events from Claude
  (`claude-sonnet-5-5`; `claude-haiku-4-5` rewrites follow-up questions for search). Without an
  API key, an offline fake model is used.
  - Sources are chosen within a budget, and each `[n]` is one chunk.
  - A question is refused without calling the model when nothing is found, and the
    `NO_ANSWER` marker is caught before it reaches the user.
  - Citation numbers are validated, and every source is kept as a snapshot, so old answers
    survive document changes ([ADR 0009](docs/adr/0009-grounded-answers.md)).
  - In the web app, citations open the quoted passage or the chunk in its document, and answers
    without citations are marked unverified.
- **Evaluation:** a labelled, synthetic corpus of 23 Indonesian and English documents with 81
  questions.
  - `knowvault eval-retrieval` compares the hybrid, vector and full-text modes
    ([ADR 0007](docs/adr/0007-retrieval-evaluation.md)).
  - `knowvault eval-answers` measures refusal accuracy, invalid citations, citations of the
    evidence and prompt-injection leaks.
  - Each answer run writes a sheet of 30 answers for manual review, which
    `knowvault eval-review` totals ([ADR 0010](docs/adr/0010-answer-evaluation.md)).
- **Limits and security** ([ADR 0011](docs/adr/0011-hardening.md)):
  - per-user limits on questions, searches, uploads and documents, plus a daily token quota;
  - per-address limits on failed logins and registrations, believing `X-Forwarded-For` from
    trusted proxies only;
  - a nonce-based Content Security Policy on every page and strict headers on API responses;
  - deletion of an account with all its data and files.
- **Production** ([ADR 0012](docs/adr/0012-production-and-e2e.md)):
  - multi-stage, non-root images;
  - `compose.prod.yaml` with Caddy (automatic TLS, HSTS, unbuffered `/api/*` and streaming)
    in front of read-only API and worker containers;
  - a backup procedure.
- **Quality:**
  - CI runs ruff, mypy (strict), import-linter, pytest against PostgreSQL with pgvector,
    ESLint, TypeScript, Vitest, a production build, an OpenAPI drift check, dependency audits
    (`pip-audit`, `npm audit`) and a Playwright end-to-end test of the critical path.

### Measured

- **Retrieval** (bge-m3, 71 answerable questions): hybrid Success@1 94.4%, Success@5 100%,
  MRR@10 0.972; vector 90.1% / 100% / 0.947
  ([report](eval/reports/2026-10-03-1450-retrieval-injection-docs.md)). Hybrid search wins on
  identifiers that differ only in character order.
- **Answers** with the fake extractive model (a pipeline check and the floor a language model
  must beat): refusal accuracy 80.2%, 0 invalid citations, evidence among the sources for every
  answerable question ([report](eval/reports/2026-10-03-1452-answers-fake-llm.md)).

### Known limitations

- **Answers have not been measured with Claude yet.** The MVP's definition of done asks for an
  answer evaluation with a real model and a manual review of about 30 answers; both need an
  Anthropic API key and are planned for the next release. Until then, the answer quality of
  this release is not quantified.
- **Not yet done from the definition of done:** no public demo or demo video, no screenshots in
  the README, and test coverage of the core modules is not measured.
- **Not supported yet:** OCR for scanned PDFs, sentence-level citations (a citation shows its
  whole chunk), and more than one machine (files are on a local volume, one worker).
- The corpus and questions are synthetic and written by the same author; compare evaluation
  runs with each other rather than reading them as production quality.

[0.1.0]: https://github.com/Fathul2703/knowvault/releases/tag/v0.1.0
