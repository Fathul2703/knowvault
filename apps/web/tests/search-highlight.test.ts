import { describe, expect, it } from "vitest";

import { highlightSegments, makeSnippet, queryTerms } from "@/features/search/highlight";

describe("queryTerms", () => {
  it("keeps words and codes, lower-cased and unique", () => {
    expect(queryTerms("Error ERR_4711 error")).toEqual(["error", "err_4711"]);
  });

  it("drops operators, excluded words and single characters", () => {
    expect(queryTerms('"connection timeout" OR retry -storage a')).toEqual([
      "connection",
      "timeout",
      "retry",
    ]);
  });

  it("handles Indonesian and other scripts", () => {
    expect(queryTerms("Bagaimana sitasi menyimpan halaman?")).toEqual([
      "bagaimana",
      "sitasi",
      "menyimpan",
      "halaman",
    ]);
    expect(queryTerms("café naïve")).toEqual(["café", "naïve"]);
  });
});

describe("highlightSegments", () => {
  it("marks matches case-insensitively and keeps the original text", () => {
    expect(highlightSegments("Timeout after a TIMEOUT.", ["timeout"])).toEqual([
      { text: "Timeout", match: true },
      { text: " after a ", match: false },
      { text: "TIMEOUT", match: true },
      { text: ".", match: false },
    ]);
  });

  it("prefers the longest term", () => {
    const segments = highlightSegments("timeouts", ["time", "timeouts"]);
    expect(segments).toEqual([{ text: "timeouts", match: true }]);
  });

  it("treats regular-expression characters literally", () => {
    expect(highlightSegments("use c++ (twice)", ["c++", "(twice)"])).toEqual([
      { text: "use ", match: false },
      { text: "c++", match: true },
      { text: " ", match: false },
      { text: "(twice)", match: true },
    ]);
  });

  it("returns the text unchanged without terms", () => {
    expect(highlightSegments("plain", [])).toEqual([{ text: "plain", match: false }]);
  });
});

describe("makeSnippet", () => {
  const long = `${"intro ".repeat(100)}the ERR_4711 code appears here ${"outro ".repeat(100)}`;

  it("keeps short text whole", () => {
    expect(makeSnippet("short text", ["text"])).toEqual({
      text: "short text",
      clippedStart: false,
      clippedEnd: false,
    });
  });

  it("centres the window on the first match", () => {
    const snippet = makeSnippet(long, ["err_4711"], 120);
    expect(snippet.text).toContain("ERR_4711");
    expect(snippet.text.length).toBeLessThanOrEqual(120);
    expect(snippet.clippedStart).toBe(true);
    expect(snippet.clippedEnd).toBe(true);
    expect(snippet.text.startsWith(" ")).toBe(false);
  });

  it("starts at the beginning when nothing matches", () => {
    const snippet = makeSnippet(long, ["absent"], 120);
    expect(snippet.text.startsWith("intro")).toBe(true);
    expect(snippet.clippedStart).toBe(false);
  });
});
