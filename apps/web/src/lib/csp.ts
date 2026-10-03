/**
 * Content Security Policy of the web app. Scripts run only from this origin and with the
 * per-request nonce Next.js adds to its own scripts; nothing may frame the app; forms, base URLs
 * and plugins are locked down. Development needs `eval` (React's error overlay) and inline
 * styles (the development tools).
 */
export function contentSecurityPolicy(nonce: string, development: boolean): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' ${development ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

/** A fresh, unguessable nonce for one response. */
export function newNonce(): string {
  return btoa(crypto.randomUUID());
}
