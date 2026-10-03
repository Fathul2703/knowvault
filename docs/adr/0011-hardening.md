# ADR 0011: Limits, client addresses, security headers and account deletion

- Status: Accepted
- Date: 2026-10-03

## Context

Before the MVP is shown to anyone, the expensive endpoints need limits, login needs protection
against trying many accounts from one place (deferred in ADR 0002), the web app needs a
Content Security Policy, and users need to be able to delete their account with all their data
(docs/ARCHITECTURE.md §13, §20). The production reverse proxy (Caddy, ADR 0003) is set up
with the release; the API has to be ready for it without depending on it.

## Decision

### Per-user limits

Fixed-window counters in PostgreSQL (`usage_counters`), as for logins, so limits hold across
API processes. Defaults, all configurable:

| What | Limit |
|---|---|
| Questions | 10 per minute, counted in the same transaction that accepts the question, plus the daily token quota (ADR 0009) |
| Searches | 60 per minute |
| Uploads, note saves and reprocessing (each queues parsing and embedding) | 120 per hour |
| Documents and notes per account | 2,000 |

Exceeding a rate returns 429 with `Retry-After`. The document limit returns 409
`document_quota_exceeded`, because waiting does not help.

### Client addresses

- **Which address counts.** `X-Forwarded-For` is believed only when the connection comes from
  an address in `TRUSTED_PROXIES`, and it is read from the right. The first address that is not
  a trusted proxy is the client; anything to its left may have been written by the client.
  With no trusted proxies, the client is the peer of the connection.
- **Why the dev proxy is not trusted.** The Next.js development proxy keeps a client-supplied
  `X-Forwarded-For` unchanged (it only sets the header when it is missing). Trusting it would
  let any client choose its own address, so `TRUSTED_PROXIES` stays empty in development and
  every request counts against the proxy's address. The production proxy must overwrite or
  append the header, and only it is trusted.
- **Limits per address:**
  - 50 failed logins per 15 minutes, across all emails. This adds to the 5 per email, against
    trying many accounts.
  - 10 registration attempts per hour, against guessing invite codes.

### Security headers

- **Web pages: nonce-based CSP.** `src/proxy.ts` creates a fresh nonce for every page and sets
  `script-src 'self' 'nonce-…' 'strict-dynamic'`; Next.js adds the nonce to its own scripts and
  styles. The policy also sets `default-src 'self'`, `object-src 'none'`,
  `frame-ancestors 'none'`, `base-uri 'self'` and `form-action 'self'`. Development
  additionally allows `'unsafe-eval'` and inline styles, which React's development tools need.
- **Pages render per request.** The root layout awaits `connection()`: a prerendered page would
  carry no nonce, and its scripts would be blocked. The app is behind a login, so static
  rendering brought little.
- **API responses** are data, never pages: `Content-Security-Policy: default-src 'none';
  frame-ancestors 'none'; sandbox`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Resource-Policy: same-origin`, `X-Content-Type-Options: nosniff` and
  `Cache-Control: no-store`. The development-only interactive docs are exempt.
- **HSTS** belongs to the TLS-terminating proxy and comes with the production setup.

### Account deletion

`DELETE /api/v1/auth/me` requires the current password. A wrong password counts as a failed
login for that email, so the endpoint cannot be used to guess the password.

The deletion runs in one transaction:
- the user row is deleted, and documents, chunks, notes, collections, conversations, messages,
  citations, traces and sessions go with it (`ON DELETE CASCADE`);
- the user's usage counters are deleted;
- invites the user redeemed keep only `used_by = NULL`.

The stored files are deleted after the commit. A failure there is logged and leaves only an
orphaned file. The identity module reads documents' storage keys through a lightweight table
reference, so it does not depend on the library module. The web app adds an Account page with
this "danger zone".

### Dependency audits

- **New CI job:** `pip-audit` on the locked runtime Python dependencies and
  `npm audit --omit=dev --audit-level=high`.
- **Development tools are not audited in CI.** Five advisories in `eslint-config-next`'s
  dependencies (`micromatch`) would otherwise fail every build without affecting what runs;
  Dependabot (already configured) keeps those tools updated.

## Consequences

- Limits apply per account and per address; a shared office address may hit the address limits
  first, which is acceptable at this scale and configurable.
- All pages are rendered on demand. Responses cannot be cached by a CDN, which this app does
  not use.
- Until the production proxy exists and is listed in `TRUSTED_PROXIES`, per-address limits in a
  proxied deployment count all clients together: safe, but strict.
