export const SESSION_COOKIE_NAMES = ["kv_session", "__Host-kv_session"] as const;

export const DEFAULT_AUTHENTICATED_PATH = "/dashboard";

/**
 * Returns `next` only if it is a same-site path, so a crafted login link cannot
 * redirect the user to another website after they sign in.
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return DEFAULT_AUTHENTICATED_PATH;
  }
  return next;
}

export function loginPathFor(pathname: string): string {
  return `/login?next=${encodeURIComponent(pathname)}`;
}
