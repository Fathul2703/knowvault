# ADR 0010: Answer evaluation

- Status: Accepted
- Date: 2026-10-03

## Context

The assistant (ADR 0009) guarantees at runtime only that citation numbers point at sources it
was given. Whether it refuses when the documents do not answer, cites the passage that holds
the answer, and resists instructions planted in documents has to be measured
(docs/ARCHITECTURE.md §10.4). The MVP plan asks for cheap automatic measures plus a structured
manual review of about 30 answers; an LLM judge is postponed until it can be calibrated
against such manual labels (Phase 5).

## Decision

- **One dataset for retrieval and answers.** The answer evaluation reuses the retrieval corpus
  and questions, so the evidence labels that judge retrieved chunks also judge cited sources.
  It adds:
  - two documents with prompt-injection attempts among ordinary content — an HTML comment in
    English and a plain paragraph in Indonesian;
  - four `injection` questions about them, each with a `canary`: text that appears in an
    answer only if the model obeyed the planted instructions;
  - two more unanswerable questions (10 in total).

  The dataset now has 23 documents and 81 questions.
- **`knowvault eval-answers`** answers every question in a new conversation through the
  production `AnswerService` (hybrid retrieval, context assembly, prompt, streaming,
  `NO_ANSWER` detection, citation checks, persistence) in a disposable `*_eval` database,
  with the chat model from `LLM_PROVIDER`.
- **Automatic measures:**
  - answer rate for answerable questions and refusal rate for unanswerable ones;
  - refusal accuracy: right decisions over all questions, with errors counted as wrong;
  - answers with invalid citation numbers;
  - answers citing a source that contains the labelled evidence;
  - whether retrieval gave the model the evidence at all, which separates retrieval misses
    from generation misses;
  - canary leaks, checked in the stored answer and in the streamed text, because streamed
    text was visible before a refusal replaced it;
  - latency and tokens.

  The report lists every failure by kind.
- **Manual review.** The run samples 30 complete answers reproducibly (fixed seed) into a
  Markdown sheet. For each citation, the reviewer ticks whether the passage supports the
  sentence citing it (`supports` / `partly` / `does not support`); for each answer, whether it
  is `faithful`, `partly faithful` or `unfaithful`. `knowvault eval-review` totals a filled
  sheet and lists sections left unmarked or marked twice. Filled sheets are committed in
  `eval/reviews/`.
- **The fake model's report is committed as a floor.** It is labelled as a pipeline check.

## Results so far

Fake extractive model, bge-m3 retrieval ([report](../../eval/reports/2026-10-03-1452-answers-fake-llm.md)):

| Measure | Value |
|---|---|
| Answerable questions answered | 90.1% (64/71) |
| Unanswerable questions refused | 10.0% (1/10) |
| Refusal accuracy | 80.2% |
| Answers with invalid citation numbers | 0 of 73 |
| Answers citing the evidence | 73.4% (47/64) |
| Evidence among the sources given | 100% (71/71) |
| Prompt-injection leaks | 0 of 4 |

As expected, word overlap alone answers almost every unanswerable question, and it cites the
wrong passage a quarter of the time, mostly for cross-lingual questions. Retrieval is not the
bottleneck: every answerable question had its evidence among the sources. The leak count says
nothing about resistance here, because the fake model cannot follow instructions. These are the
numbers a language model must beat.

No run with Claude is recorded yet: it needs an API key and is a paid run (about 90,000 input
tokens for the whole dataset). Running `make eval-answers-docker` with
`LLM_PROVIDER=anthropic`, then filling in the review sheet, completes the MVP's answer
evaluation (§20).

## Consequences

- The same evidence labels keep retrieval and answer numbers comparable across changes to
  chunking, prompts or models.
- Four injection questions show whether a model obeys planted text, not how robust it is in
  general; the set should grow with real attempts.
- Targets for refusal accuracy and citation quality are set after the first Claude baseline,
  as §20 requires, not before.
