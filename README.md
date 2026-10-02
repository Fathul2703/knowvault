# KnowVault

Personal knowledge management with AI answers that are grounded in your own documents and
cite their sources.

> **Status: Phase 3 — Retrieval (hybrid search).** Accounts, collections, notes and document
> upload work end to end: a background worker extracts the text of PDF, Word, Markdown and text
> files, splits it into chunks that keep their page or section, and embeds each chunk with
> BAAI/bge-m3 (multilingual, run locally). A search API combines semantic and keyword search
> with Reciprocal Rank Fusion; the **Search** page shows the matching passages and links to
> the exact chunk. A retrieval evaluation is next; cited Q&A arrives in Phase 4. See the [roadmap](docs/ARCHITECTURE.md#5-feature-roadmap-phase-16).

## Stack

| Part | Technology |
|---|---|
| Web | Next.js 16 (App Router), TypeScript, Tailwind CSS 4, TanStack Query |
| API | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic |
| Worker | Same codebase as the API; PostgreSQL job queue; `pypdf`, `python-docx` in a sandboxed child process |
| Embeddings | BAAI/bge-m3 (int8 ONNX, 1024 dimensions) via fastembed / ONNX Runtime, on CPU |
| Database | PostgreSQL 17 with pgvector 0.8 (HNSW index, cosine distance) and full-text search (GIN) |
| Dev environment | Docker Compose |

The browser only talks to the Next.js server, which forwards `/api/*` to FastAPI. Sessions are
server-side, stored as hashed tokens in PostgreSQL. Uploads are stored on disk and queued; the
worker processes them and the web app polls until they are ready. More in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the [ADRs](docs/adr/).

## Quick start (Docker)

Requirements: Docker with Compose v2, with at least 4 GB of memory for Docker (the API and the
worker each load the embedding model, about 1 GB apiece).

```bash
git clone https://github.com/Fathul2703/knowvault.git
cd knowvault
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, applies migrations, then runs the API on http://localhost:8000, the
document worker, and the web app on http://localhost:3000. The first build takes a few minutes.

The embedding model (569 MB) is downloaded the first time a document is processed or a search
runs. To fetch it up front: `make model-docker`. If you are upgrading from Phase 2, embed the
documents you already have with `make reindex-docker`.

Registration is invite-only. In a second terminal, create an invite:

```bash
docker compose exec api knowvault create-invite
```

Open http://localhost:3000/register, paste the code and create your account.

> If port 5432 is already in use on your machine (for example by a Homebrew PostgreSQL), change
> `POSTGRES_PORT` **and** the ports in `DATABASE_URL` and `TEST_DATABASE_URL` — see
> [Database ports](#database-ports-host-vs-containers).

### Database ports: host vs. containers

The database is reached in two different ways, and they use different addresses:

| Connection | Address | Configured by |
|---|---|---|
| Container → container (`migrate`, `api`, `docker compose exec api pytest`) | `db:5432` (service name, PostgreSQL's internal port) | `compose.yaml`, built from `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Host → container (`make api`, `make migrate`, `make invite`, `make test-api`, `make check`, GUI clients) | `localhost:<POSTGRES_PORT>` | `DATABASE_URL` and `TEST_DATABASE_URL` in `.env` |

`POSTGRES_PORT` only chooses the host port that Compose publishes. The containers always use
`db:5432`, and Compose ignores `DATABASE_URL` and `TEST_DATABASE_URL` from `.env`. Commands that
run on your machine, however, read those two URLs, so **their port must equal `POSTGRES_PORT`**.
If they do not match, host commands connect to whatever else listens on that port — or fail.

Example: Homebrew PostgreSQL already listens on 5432, so the Docker database is published on 5433.
The relevant lines of `.env`:

```dotenv
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://knowvault:change-me-dev-only@localhost:5433/knowvault
TEST_DATABASE_URL=postgresql+asyncpg://knowvault:change-me-dev-only@localhost:5433/knowvault_test
```

With these values the containers still talk to `db:5432`, while `make check` on your machine
tests against the Docker database on `localhost:5433` and leaves the Homebrew server untouched.
To use the Homebrew server for host commands instead, point both URLs at `localhost:5432` with
that server's credentials.

**`.env` wins inside `make`.** Every `make` target that needs configuration sources `.env` right
before running its command, so a value in `.env` replaces a variable you exported in your shell
(for example `export TEST_DATABASE_URL=…` has no effect on `make test-api` if `.env` also sets
it). Change the value in `.env`, or run the underlying command without `make`. Docker Compose
behaves the other way round: when it fills in `${POSTGRES_PORT}` and similar values in
`compose.yaml`, a variable exported in your shell takes precedence over `.env`.

## Local development without Docker

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 22.12+, and PostgreSQL 17 you can
create databases on.

```bash
cp .env.example .env     # then set DATABASE_URL and TEST_DATABASE_URL to your PostgreSQL
make install             # uv sync + npm ci
createdb knowvault       # or create it with your usual tool; must match DATABASE_URL
make migrate
make invite
make api                 # terminal 1: http://localhost:8000
make worker              # terminal 2: processes uploads and notes
make web                 # terminal 3: http://localhost:3000
```

`make` loads `.env` automatically, and its values replace variables already exported in your
shell (see [Database ports](#database-ports-host-vs-containers)). Without `make`, export the
variables from `.env` yourself.

## Checks

```bash
make check      # lint + type checks + all tests (what CI runs)
make test-api   # API tests; needs TEST_DATABASE_URL
make test-web   # web tests
```

API tests run against a real PostgreSQL database **with the pgvector extension** (the Compose
database has it; a plain Homebrew PostgreSQL does not). The database named in
`TEST_DATABASE_URL` is **dropped and recreated** on every run, so its name must end in `_test`.
With Docker you can run them inside the stack: `docker compose exec api pytest`.

Tests use deterministic fake embeddings and never download the model. To also check the real
bge-m3 model, point `KNOWVAULT_TEST_MODEL_DIR` at a model cache directory (it is downloaded
there if missing) and run `make test-api`.

After changing API endpoints or schemas, run `make openapi` to regenerate
`apps/api/openapi.json` and the web app's types. CI fails if they are out of date.

## Configuration

All configuration comes from environment variables; see [`.env.example`](.env.example).
Secrets are never committed.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Compose | Database container credentials; `POSTGRES_PORT` is the host port only (containers use `db:5432`) |
| `DATABASE_URL` | API on the host | `postgresql+asyncpg://…@localhost:<POSTGRES_PORT>/…`; ignored by Compose, which builds its own |
| `TEST_DATABASE_URL` | API tests on the host | Disposable test database on `localhost:<POSTGRES_PORT>`; name must end in `_test` |
| `APP_ORIGIN` | API | Origin of the web app; other origins cannot make state-changing requests |
| `SESSION_COOKIE_SECURE` | API | `true` in production (HTTPS); required when `ENVIRONMENT=production` |
| `ENVIRONMENT`, `LOG_LEVEL` | API | `development`, `test` or `production`; log verbosity |
| `STORAGE_DIR` | API, worker on the host | Directory for uploaded files, relative to `apps/api`; Compose uses the `uploads` volume |
| `MAX_UPLOAD_MB`, `MAX_PAGES`, `MAX_EXTRACTED_CHARS`, `MAX_NOTE_CHARS` | API, worker | Optional limits (defaults 25 MB, 500 pages, 5,000,000 and 200,000 characters). If you raise `MAX_UPLOAD_MB`, raise `proxyClientMaxBodySize` in `apps/web/next.config.ts` too |
| `PARSE_TIMEOUT_SECONDS`, `PARSE_MEMORY_MB` | Worker | Optional limits for the parser process (defaults 60 s, 1024 MB; memory is enforced on Linux only) |
| `EMBEDDING_PROVIDER` | API, worker | `bge-m3` (default) or `fake` (tests only; refused in production) |
| `EMBEDDING_CACHE_DIR` | API, worker on the host | Where the model is stored, relative to `apps/api`; Compose uses the `models` volume |
| `EMBEDDING_THREADS`, `EMBEDDING_BATCH_SIZE` | API, worker | Optional ONNX Runtime threads per process and chunks per batch (defaults: runtime's choice, 8) |
| `API_INTERNAL_URL` | Web | Where the Next.js server forwards `/api/*` |

## Admin commands

```bash
knowvault create-invite [--days N]   # single-use registration invite
knowvault reset-password EMAIL       # prompts for a new password, signs the user out everywhere
knowvault export-openapi             # prints the OpenAPI schema
knowvault worker                     # runs the document worker (the `worker` service in Compose)
knowvault download-model             # downloads the embedding model now instead of on first use
knowvault reindex [--all]            # queues documents embedded by another model (or not at all)
```

Run them with `docker compose exec api …` or, locally, `cd apps/api && uv run …` with the
environment loaded.

## Library

- **Supported files:** PDF, Word (`.docx`), Markdown (`.md`) and plain text (`.txt`), up to
  25 MB and 500 pages. The type is detected from the file's content, not its name or the
  browser's declared type. Uploading the same file twice is refused.
- **Processing:** each upload or note edit is queued. The worker extracts the text in a
  separate, time- and memory-limited process, normalises it and splits it into chunks of about
  1,800 characters that never cross a heading. PDF chunks keep their page numbers; other
  formats keep their heading trail. Open a document to see exactly what was extracted.
- **Failures** are shown with a reason (for example, scanned PDFs without a text layer are not
  supported yet) and can be retried with **Try again**.
- **Collections** group documents; deleting a collection keeps its documents.

## Search

The **Search** page (`/search`) finds passages across your ready documents and notes.

- **Best match** (default) combines meaning and exact words; **Meaning** finds paraphrases,
  also across Indonesian and English; **Exact words** matches names, codes and
  `"quoted phrases"`, with `-word` to exclude and `OR` for alternatives.
- Each result shows its document, page range or section, the passage with the query's words
  highlighted, which method found it and how similar it is.
- Clicking a result opens the document scrolled to that passage (`/library/<id>#chunk-<n>`).
- The query, mode and collection live in the URL, so searches can be bookmarked and shared,
  and back/forward work.
- The first search after the API starts loads the embedding model and can take up to about
  half a minute; the page says so while it waits.

## API

- Health: `GET /healthz` (process up), `GET /readyz` (database reachable)
- Library: `/api/v1/collections`, `/api/v1/documents` (upload, list, detail, `/file`,
  `/chunks`, `/reprocess`), `/api/v1/notes`
- Search: `POST /api/v1/retrieval/search` with `{"query": "...", "top_k": 8}` and optional
  `collection_id`, `document_ids` and `mode`. It searches the signed-in user's ready documents.
  - `hybrid` (default): semantic search (bge-m3, cosine) and keyword search (PostgreSQL
    full text, `simple` configuration) fused with Reciprocal Rank Fusion. Good for both
    paraphrased questions and exact terms such as names or error codes.
  - `vector` or `fulltext`: one method only, for debugging and evaluation. Full-text queries
    support `"quoted phrases"`, `-exclusions` and `OR`.

  Each result has its document, page range or heading trail, `score` (meaning depends on the
  mode), cosine `similarity`, and its rank in each method. The user always comes from the
  session; a `user_id` in the body is rejected.
- Interactive docs (development only): http://localhost:8000/api/docs
- Errors use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details with a stable `code`.

## Project structure

```
apps/
  api/                 FastAPI app, Alembic migrations, tests
    src/knowvault/
      core/            config, database, errors, logging, middleware, rate limiting, job queue,
                       storage port, health
      adapters/        port implementations (filesystem storage, bge-m3 and fake embeddings)
      modules/
        identity/      users, sessions, invites, auth endpoints
        library/       collections, documents, notes, uploads; `processing.py` for ingestion
        ingestion/     domain (normalise, chunk) → application (pipeline, embedding) →
                       infrastructure (parsers, parser process, chunks) → api
        retrieval/     domain (RRF) → application (search) → infrastructure (pgvector,
                       full-text) → api
      main.py          API composition root
      worker.py        worker composition root
      cli.py           admin commands
  web/                 Next.js app
    src/app/           routes: login, register, dashboard, library, library/[id], library/notes/…,
                       search
    src/features/      auth, dashboard, library, search
    src/lib/api/       typed API client and generated types
docs/                  architecture and ADRs
compose.yaml           development stack
Makefile               developer commands (`make help`)
```

## License

Not yet chosen.
