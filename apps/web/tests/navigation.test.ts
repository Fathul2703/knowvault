import { describe, expect, it } from "vitest";

import { DEFAULT_AUTHENTICATED_PATH, loginPathFor, safeNextPath } from "@/lib/navigation";

describe("safeNextPath", () => {
  it.each(["/library", "/dashboard?tab=1"])("keeps same-site path %s", (path) => {
    expect(safeNextPath(path)).toBe(path);
  });

  it.each([
    undefined,
    null,
    "",
    "https://evil.example",
    "//evil.example/path",
    "/\\evil.example",
    "library",
  ])("rejects %s", (value) => {
    expect(safeNextPath(value)).toBe(DEFAULT_AUTHENTICATED_PATH);
  });
});

describe("loginPathFor", () => {
  it("encodes the return path", () => {
    expect(loginPathFor("/library?x=1&y=2")).toBe("/login?next=%2Flibrary%3Fx%3D1%26y%3D2");
  });
});
