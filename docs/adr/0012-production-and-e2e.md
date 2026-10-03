# ADR 0012: Production images, Caddy and end-to-end tests

- Status: Accepted; completes ADR 0003
- Date: 2026-10-03

## Context

ADR 0003 postponed the reverse proxy and production images to Phase 4. In development the
Next.js server proxies `/api/*`, which buffers request bodies and passes a client-supplied
`X-Forwarded-For` through (ADR 0011). The MVP also needs an end-to-end test of the critical path
in CI (docs/ARCHITECTURE.md §14, §20).

## Decision

### Images

Each Dockerfile has a `dev` target (unchanged) and a `prod` target.

- **API, worker and migrations** share one image:
  - a build stage installs only the locked runtime dependencies and the project, not editable;
  - the final stage has the virtualenv, `alembic.ini` and `migrations/`, and runs as uid 10001;
  - uvicorn runs without `--reload`, and with its own proxy-header handling and server header
    turned off, because the application interprets `X-Forwarded-For` itself (ADR 0011).
- **Web:** Next.js `output: "standalone"`. The final stage holds the server and static files
  only, and runs as the `node` user.

### Production stack (`compose.prod.yaml`)

- **Caddy is the only service with published ports** (80, 443 including HTTP/3). It obtains
  certificates automatically and sets HSTS (`HSTS_MAX_AGE`, 0 for a trial on `localhost`).
- **Routing:**
  - `/api/*` goes straight to FastAPI with `flush_interval -1`, so uploads are not buffered and
    answers stream event by event;
  - everything else goes to Next.js, with compression.
- **Client addresses.** Caddy has a fixed address on the internal network (`172.30.0.10`).
  That address is the API's only `TRUSTED_PROXIES` entry, and Caddy replaces any
  `X-Forwarded-For` sent by clients.
- **Containers:**
  - API, worker and migrations run with read-only root file systems, a tmpfs `/tmp`
    (`HOME=/tmp`), no Linux capabilities and `no-new-privileges`;
  - the uploads and model volumes are the only writable paths;
  - the database is not published.
- **Settings refuse unsafe production configurations:** fake models, insecure cookies, an origin
  without HTTPS. `ENVIRONMENT` can be overridden only for a local trial.

### End-to-end tests

- **Stack.** `compose.e2e.yaml` runs the production images with the fake embedding and chat
  models (allowed outside production), a tmpfs database and the web app on port 3100. Next.js
  proxies `/api/*`, as in development, so the streaming check also covers that path.
- **Test.** One Playwright test walks the critical path through the UI: register with an
  invite created by the admin CLI, write a note and wait until it is ready, search, ask, open
  the cited passage and its chunk, get a refusal, and delete the account.
- **Where it runs.** `make e2e` runs it locally; CI runs it as the "E2E (Playwright)" job and
  uploads the trace on failure.

## Verification

- **Production stack, locally** (`DOMAIN=localhost`, fake LLM, real bge-m3):
  - HTTP/2 over TLS, HTTP redirected to HTTPS, HSTS and the nonce CSP present, no `Server`
    header, the `__Host-` session cookie set;
  - the model downloaded into its volume despite read-only containers;
  - upload, search and a streamed answer worked through Caddy;
  - a write to `/app` was refused, and the API runs as uid 10001.
- **The end-to-end test found a real bug** that unit and API tests had missed. Deleting a user
  who had answers citing their own documents failed: each citation was reached twice in one
  statement (deleted through conversations, set to NULL through chunks), and PostgreSQL
  rejected the update of a row whose message was already gone. Conversations are now deleted
  first, and an API test reproduces the case.

## Consequences

- One `docker compose` command deploys a single host; no orchestrator is needed at this scale.
- Every page is rendered per request (ADR 0011) by the standalone Next.js server.
- E2E runs add a few minutes to CI, mostly image builds.
