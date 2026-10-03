import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, newNonce } from "@/lib/csp";
import { isGuarded } from "@/proxy";

describe("contentSecurityPolicy", () => {
  it("allows only same-origin scripts carrying the nonce in production", () => {
    const policy = contentSecurityPolicy("abc", false);
    expect(policy).toContain("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(policy).toContain("style-src 'self' 'nonce-abc'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).not.toContain("unsafe");
  });

  it("relaxes only what the development tools need", () => {
    const policy = contentSecurityPolicy("abc", true);
    expect(policy).toContain("'unsafe-eval'");
    expect(policy).toContain("style-src 'self' 'unsafe-inline'");
  });

  it("makes a different nonce every time", () => {
    expect(newNonce()).not.toBe(newNonce());
  });
});

describe("isGuarded", () => {
  it.each([
    ["/chat", true],
    ["/chat/abc", true],
    ["/account", true],
    ["/library/x", true],
    ["/login", false],
    ["/", false],
    ["/chatter", false],
  ])("%s → %s", (path, guarded) => {
    expect(isGuarded(path)).toBe(guarded);
  });
});
