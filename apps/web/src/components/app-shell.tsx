"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Badge, Button } from "@/components/ui";
import { useCurrentUser, useLogout } from "@/features/auth/hooks";
import { loginPathFor } from "@/lib/navigation";

type NavItem = { href: string; label: string; availableIn?: string };

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/library", label: "Library" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Ask" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const user = useCurrentUser();
  const logout = useLogout();

  // Full page loads reset all client state, so nothing from the old session survives.
  const signOut = (destination: string) =>
    logout.mutate(undefined, { onSettled: () => window.location.assign(destination) });

  const unauthenticated = user.error?.status === 401;
  useEffect(() => {
    if (unauthenticated) {
      // The cookie exists but the session is no longer valid: clear it, then sign in again.
      signOut(loginPathFor(pathname));
    }
    // Only react to the session becoming invalid.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unauthenticated]);

  if (!user.data) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        {user.isError && !unauthenticated ? (
          <div className="space-y-3 text-center">
            <p>Could not reach the KnowVault API.</p>
            <Button variant="secondary" onClick={() => user.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          <p aria-live="polite">Loading…</p>
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="px-5 py-5 text-lg font-semibold tracking-tight">KnowVault</div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 px-3">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} />
          ))}
        </nav>
        <div className="border-t border-slate-200 px-5 py-4 text-sm">
          <p className="truncate font-medium text-slate-900">{user.data.display_name}</p>
          <p className="truncate text-slate-500">{user.data.email}</p>
          <Button
            variant="ghost"
            className="-ml-3.5 mt-2"
            disabled={logout.isPending}
            onClick={() => signOut("/login")}
          >
            Sign out
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="space-y-2 border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <span className="block font-semibold">KnowVault</span>
          {/* Its own row, scrollable as a last resort, so no item is ever cut off. */}
          <nav aria-label="Mobile" className="-mx-2 flex items-center gap-0.5 overflow-x-auto">
            {NAV_ITEMS.filter((item) => !item.availableIn).map((item) => (
              <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} />
            ))}
            <Button
              variant="ghost"
              className="ml-auto whitespace-nowrap px-2"
              disabled={logout.isPending}
              onClick={() => signOut("/login")}
            >
              Sign out
            </Button>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">{children}</main>
      </div>
    </div>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const base = "flex items-center justify-between whitespace-nowrap rounded-md px-2.5 py-2 text-sm";
  if (item.availableIn) {
    return (
      <span className={`${base} cursor-not-allowed text-slate-400`} aria-disabled="true">
        {item.label}
        <Badge>{item.availableIn}</Badge>
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`${base} ${
        active ? "bg-brand-50 font-medium text-brand-700" : "text-slate-600 hover:bg-slate-100"
      }`}
    >
      {item.label}
    </Link>
  );
}
