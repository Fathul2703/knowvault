# ADR 0004: Document ingestion in Phase 2

- Status: Accepted; chunk sizes changed in ADR 0014
- Date: 2026-09-29

## Context

Phase 2 stores uploaded files and notes and turns them into chunks that Phase 3 will embed
and search. The parsers read untrusted files; processing must survive crashes and be retried;
`docs/ARCHITECTURE.md` left the parser libraries (D6) and limits (D9) open.

## Decision

- **Parsers:** `pypdf` (BSD) for PDF and `python-docx` (MIT) for Word. Markdown and plain text
  are parsed without dependencies (ATX headings, code fences respected). PyMuPDF is avoided
  because it is AGPL-licensed.
- **Isolation:** the worker runs every parse in a child process
  (`python -m knowvault.modules.ingestion.infrastructure.parse_entry`) with a hard timeout
  (60 s) and, on Linux, an address-space limit (1 GB). A document that times out or exceeds a
  limit fails permanently with a readable reason; a child that dies without answering is
  treated as a transient error and retried.
- **Limits:** 25 MB per upload (checked while streaming, and by an ASGI middleware on the raw
  request body), 500 pages, 5 million extracted characters, 200,000 characters per note.
  File types are detected from content (PDF signature, DOCX archive layout, UTF-8 text plus the
  `.md`/`.txt` extension), never from the client's `Content-Type`.
- **Job queue:** one generic `jobs` table in `core` (`type`, `resource_id`, JSON `payload`),
  claimed with `FOR UPDATE SKIP LOCKED`. It has no foreign key to `documents`, so `core` does
  not depend on a feature module; a job whose document was deleted completes without work.
  A partial unique index coalesces queued jobs for the same resource, which turns bursts of
  note edits into one run.
- **Consistency:** each document has a `content_version`. The worker computes chunks outside
  the database, then in one transaction locks the document row, checks the version, replaces
  all chunks and marks the document ready. Results for an outdated version are discarded.
- **Chunking:** structure-aware, measured in characters: target 1,800, maximum 2,400, overlap
  up to 200 characters of whole sentences or paragraphs, never across headings. Characters are
  a conservative proxy for tokens until an embedding model is chosen (D5).
- **Module boundary:** ingestion reads and updates documents only through
  `knowvault.modules.library.processing`; the library never imports ingestion. Enforced by
  import-linter together with the ingestion layer order (api → infrastructure → application →
  domain).
- Notes are shown as plain text; Markdown is not rendered to HTML in Phase 2, which avoids
  an HTML sanitiser dependency and an XSS surface.

## Consequences

- A hostile file can cost at most one parser process for 60 seconds; the worker keeps going.
- Changing chunk sizes or parsers requires reprocessing documents (the "Try again" action or a
  future bulk command).
- Uploaded files live on a local volume shared by the API and the worker, so both must run on
  the same host until an S3-compatible adapter is added.
