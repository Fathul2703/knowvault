# ADR 0009: Grounded answers with citations (assistant backend)

- Status: Accepted
- Date: 2026-10-03

## Context

Phase 4 turns search into question answering: the answer must come only from the user's
documents, cite them as `[n]`, and refuse rather than guess when the documents do not answer
the question (docs/ARCHITECTURE.md §10). This ADR records decision D4 (the language model) and
how the backend implements §10.1–§10.3. The chat UI, the answer evaluation and the hardening
of expensive endpoints are later parts of Phase 4.

## Decision

### Language model (D4)

- **Provider:** Anthropic, through the official SDK, behind a `ChatModel` port in `core`
  (`stream` and `complete`). Adapters live in `adapters/chat`; no model ID appears outside
  configuration.
- **Models:** `claude-sonnet-5-5` writes answers; `claude-haiku-4-5-20251001` rewrites
  follow-up questions into standalone search queries. Both are settings (`LLM_MODEL`,
  `LLM_FAST_MODEL`).
- **Default is a fake model** (`LLM_PROVIDER=fake`), so the stack and CI run without an API
  key. It quotes the first sentence of the sources that share words with the question and
  cites them, or replies `NO_ANSWER` when none does. It is refused in production.
- The SDK retries failed connections before a response starts; once text has streamed,
  errors are reported instead of retried, so text is never repeated. Provider errors are
  mapped to stable codes (`llm_timeout`, `llm_rate_limited`, `llm_unavailable`) without
  request content.

### Answering a question

1. **Start (one short transaction).** The user's row is locked (`FOR NO KEY UPDATE`) so that
   two requests cannot both pass the checks: the conversation must belong to the user, no
   other answer of the user may be `streaming` (one stream per user; an answer still
   streaming after 5 minutes is considered abandoned), and the daily token quota must not be
   spent. The question and an empty `streaming` answer are stored. Failures here are ordinary
   problem responses (404, 409 `answer_in_progress`, 429 `token_quota_exceeded`), returned
   before any stream starts.
2. **Condensation.** When the conversation has earlier answered turns, the fast model
   rewrites the question for search. An empty or overlong rewrite falls back to the question.
   The answer prompt still receives the original question and the history.
3. **Retrieval.** Hybrid search (ADR 0006, 0008) within the conversation's scope, top
   `2 × CHAT_MAX_SOURCES` candidates, in a session that is closed before the model is called.
4. **Context.** Up to 8 sources within 24,000 characters, chosen in relevance order (a source
   that does not fit is skipped for shorter ones), duplicates removed, grouped by document and
   ordered by position. One `[n]` is exactly one chunk.
5. **Evidence gate.** No sources: the answer is refused without calling the model. Otherwise
   the model is told to reply with exactly `NO_ANSWER` when the sources are not enough. The
   server holds back the start of the stream until it cannot be the marker any more, so the
   marker never reaches the client. A reply that starts normally but still contains the
   marker is also stored as refused; the `done` event says so and the client shows the
   standard refusal text. No similarity threshold is used (not yet calibrated, §10.2).
6. **Post-processing.** `[n]` markers (also `[2, 3]`) are checked against the sources: the
   `done` event lists valid and invalid numbers. Whether a source supports its sentence is not
   checked at runtime; that is what the answer evaluation measures.
7. **Finish (one short transaction).** The answer, its status, model, token usage and latency
   are stored with a snapshot of every source and a retrieval trace (IDs, ranks and scores, no
   document text), and the tokens are added to the user's daily counter.

### Database connections while streaming

The request's own session (used for authentication) is closed before the stream starts, and
the answer service opens short sessions for each step, so no connection is held while the
model writes (§10.2, risk R12). When the client disconnects, Starlette stops iterating but
leaves the generator suspended; the SSE response therefore always closes it, and the answer's
cleanup stores what was written with status `error` (`client_disconnected`) in a shielded
transaction.

### Data model (migration 0005)

`conversations`, `messages`, `message_citations` and `retrieval_traces` as in §7.3, with three
changes:

- `messages.seq` (identity) orders messages; a question and its answer share `created_at`.
- `messages.error_code` records why an answer failed.
- `message_citations` stores **every** source given to the model, with `cited` marking the
  ones the answer cites, so a reloaded conversation shows the same source list as the stream.
  `chunk_id` and `document_id` become null when the document is reprocessed or deleted; the
  snapshot (`document_title`, `quoted_text`, location) keeps old answers readable.

### Prompts

Prompts are code in `assistant/application/prompts.py` with `PROMPT_VERSION = "answer-v1"`,
recorded in every trace. Sources are wrapped in `<source index="n" title="..." location="...">`
tags; attributes are escaped and a document cannot close its own tag. The system prompt tells
the model to treat source text as data and never follow instructions inside it. This reduces,
but does not remove, the risk of prompt injection; the model has no tools, so the impact is
limited to the text of the answer.

## Consequences

- `make dev` and CI need no API key; setting `LLM_PROVIDER=anthropic` and
  `ANTHROPIC_API_KEY` switches to Claude without code changes.
- The daily quota is checked before an answer and counted after it, so one answer can exceed
  the limit; the next one is refused. Per-minute rate limits for chat, search and upload come
  with the hardening part of Phase 4.
- Storing all sources costs a few kilobytes per answer and keeps reloads faithful to the
  stream.
- Answer quality with Claude is not measured yet; refusal accuracy and citation validity are
  the answer evaluation's job (Phase 4, docs/ARCHITECTURE.md §10.4).
