# ADR 0002: Server-side sessions, invite-only registration and origin checks

- Status: Accepted
- Date: 2026-09-29

## Context

The app has one backend and is served from a single origin. It must be secure by default,
must not let strangers run up LLM costs on a public demo, and has no email service.

## Decision

- **Sessions:** a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie
  (`Secure` + `__Host-` prefix in production). Only its SHA-256 hash is stored in `sessions`.
  Sessions have an idle timeout (7 days) and an absolute lifetime (30 days) and can be revoked.
  No JWTs.
- **Passwords:** Argon2id via `argon2-cffi`; 12–128 characters. Hashes are upgraded on login
  when the library's parameters change. Unknown emails are verified against a dummy hash so
  both failure paths cost the same.
- **Registration** requires a single-use invite code created with `knowvault create-invite`.
  Only a hash of the code is stored. **Password resets** are done by an operator with
  `knowvault reset-password`, which also revokes the user's sessions.
- **CSRF:** state-changing `/api/*` requests are rejected when their `Origin` (or, if absent,
  `Sec-Fetch-Site`) shows a different site, and request bodies must be JSON. Requests with
  neither header come from non-browser clients and are allowed.
- **Brute force:** failed logins are counted per email in the `usage_counters` table
  (5 per 15 minutes by default). Counting in Postgres keeps the limit correct across processes.
- **Per-IP rate limiting is deferred** to Phase 4. Behind the Next.js proxy every request
  appears to come from the proxy, so a per-IP limit needs a trusted reverse proxy that sets
  forwarding headers first.

## Consequences

- Logout and password resets take effect immediately.
- An attacker who knows an email can lock that account out for one window by failing logins.
  This is accepted for Phase 1 and revisited with per-IP limits.
- Registration reveals whether an email is already registered; acceptable because it
  requires an invite.
