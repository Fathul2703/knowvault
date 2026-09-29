# KnowVault

Personal knowledge management with AI answers that are grounded in your own documents and
cite their sources.

> **Status: Phase 1 — Foundation.** Accounts, sessions, the app shell, dashboard and the
> (still empty) document library are in place. Document upload arrives in Phase 2, search in
> Phase 3 and cited Q&A in Phase 4. See the [roadmap](docs/ARCHITECTURE.md#5-feature-roadmap-phase-16).

## Stack

| Part | Technology |
|---|---|
| Web | Next.js 16 (App Router), TypeScript, Tailwind CSS 4, TanStack Query |
| API | Python 3.13, FastAPI, SQLAlchemy 2 (async), Alembic |
| Database | PostgreSQL 17 (pgvector image, used from Phase 3) |
| Dev environment | Docker Compose |

The browser only talks to the Next.js server, which forwards `/api/*` to FastAPI. Sessions are
server-side, stored as hashed tokens in PostgreSQL. More in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the [ADRs](docs/adr/).

## Quick start (Docker)

Requirements: Docker with Compose v2.

```bash
git clone https://github.com/Fathul2703/knowvault.git
cd knowvault
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL, applies migrations, then runs the API on http://localhost:8000 and the
web app on http://localhost:3000. The first build takes a few minutes.

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
make web                 # terminal 2: http://localhost:3000
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

API tests run against a real PostgreSQL database. The database named in `TEST_DATABASE_URL`
is **dropped and recreated** on every run, so its name must end in `_test`. With Docker you can
run them inside the stack: `docker compose exec api pytest`.

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
| `API_INTERNAL_URL` | Web | Where the Next.js server forwards `/api/*` |

## Admin commands

```bash
knowvault create-invite [--days N]   # single-use registration invite
knowvault reset-password EMAIL       # prompts for a new password, signs the user out everywhere
knowvault export-openapi             # prints the OpenAPI schema
```

Run them with `docker compose exec api …` or, locally, `cd apps/api && uv run …` with the
environment loaded.

## API

- Health: `GET /healthz` (process up), `GET /readyz` (database reachable)
- Interactive docs (development only): http://localhost:8000/api/docs
- Errors use [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem details with a stable `code`.

## Project structure

```
apps/
  api/                 FastAPI app, Alembic migrations, tests
    src/knowvault/
      core/            config, database, errors, logging, middleware, rate limiting, health
      modules/identity users, sessions, invites, auth endpoints
      main.py          app factory (composition root)
      cli.py           admin commands
  web/                 Next.js app
    src/app/           routes: (auth)/login, (auth)/register, (app)/dashboard, (app)/library
    src/features/      auth, dashboard, library
    src/lib/api/       typed API client and generated types
docs/                  architecture and ADRs
compose.yaml           development stack
Makefile               developer commands (`make help`)
```

## License

Not yet chosen.
