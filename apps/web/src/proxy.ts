import { NextResponse, type NextRequest } from "next/server";

import { contentSecurityPolicy, newNonce } from "@/lib/csp";
import { loginPathFor, SESSION_COOKIE_NAMES } from "@/lib/navigation";

/** Pages that need a session. */
export const GUARDED_PATHS = ["/dashboard", "/library", "/search", "/chat", "/account"] as const;

export function isGuarded(pathname: string): boolean {
  return GUARDED_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

/**
 * Runs before every page:
 * - Sends visitors without a session cookie to the login page before the app shell renders
 *   (a UX guard only: whether a session is valid is always decided by the API).
 * - Sets a Content Security Policy with a fresh nonce, which Next.js adds to its own scripts.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = SESSION_COOKIE_NAMES.some((name) => request.cookies.has(name));
  if (isGuarded(pathname) && !hasSession) {
    return NextResponse.redirect(new URL(loginPathFor(pathname + search), request.url));
  }

  const policy = contentSecurityPolicy(newNonce(), process.env.NODE_ENV === "development");
  const requestHeaders = new Headers(request.headers);
  // Next.js reads the nonce from the policy on the request while rendering.
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      // Pages only: not the API (proxied to FastAPI, which sets its own headers) or static files.
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
