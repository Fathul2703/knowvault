# ADR 0003: Development topology and test database

- Status: Accepted
- Date: 2026-09-29

## Context

The architecture document places a Caddy reverse proxy in front of the web app and the API so
the browser sees a single origin, and proposes Testcontainers for integration tests.

## Decision

- **No Caddy in Phase 1.** The Next.js server rewrites `/api/*` to the API
  (`API_INTERNAL_URL`). The browser still talks to one origin, so cookies stay first-party and
  no CORS configuration exists. Caddy (TLS, security headers, SSE without buffering,
  trusted forwarding headers) is introduced with the production setup in Phase 4.
- **Tests use a real PostgreSQL database named by `TEST_DATABASE_URL`**, recreated at the start
  of each run and migrated with Alembic. CI provides it as a service container; locally it is
  the Compose database or any PostgreSQL 17 instance. The name must end in `_test`, and the
  suite refuses to touch anything else. Testcontainers is not used: it would require Docker for
  every test run and adds a dependency without improving what is tested.
- Docker images are development images only. Production images are built in Phase 4.

## Consequences

- One service fewer to run and configure during development.
- The Next.js proxy buffers request bodies and, by default, truncates them at 10 MB, which
  corrupted larger uploads (found in Phase 2). `experimental.proxyClientMaxBodySize` in
  `apps/web/next.config.ts` is set to 32 MB, above the API's upload limit plus multipart
  overhead, so oversized uploads still reach the API whole and receive a 413. Uploads are
  therefore buffered in the Next.js server's memory in development; Caddy removes this in
  Phase 4.
- Streaming responses (Phase 4) must be re-checked through the Next.js proxy or moved behind
  Caddy.
