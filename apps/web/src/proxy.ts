import { NextResponse, type NextRequest } from "next/server";

import { loginPathFor, SESSION_COOKIE_NAMES } from "@/lib/navigation";

/**
 * UX-only guard: sends visitors without a session cookie to the login page before the app
 * shell renders. Whether a session is actually valid is always decided by the API.
 */
export function proxy(request: NextRequest) {
  const hasSession = SESSION_COOKIE_NAMES.some((name) => request.cookies.has(name));
  if (hasSession) {
    return NextResponse.next();
  }
  const { pathname, search } = request.nextUrl;
  return NextResponse.redirect(new URL(loginPathFor(pathname + search), request.url));
}

export const config = {
  matcher: ["/dashboard/:path*", "/library/:path*", "/search/:path*"],
};
