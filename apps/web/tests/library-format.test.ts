import { describe, expect, it } from "vitest";

import { chunkLocation, formatBytes, typeLabel } from "@/features/library/format";

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [1536, "1.5 KB"],
    [25 * 1024 * 1024, "25 MB"],
  ])("formats %d as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("chunkLocation", () => {
  it("uses pages when known", () => {
    expect(chunkLocation({ page_start: 3, page_end: 3, heading_path: [] })).toBe("Page 3");
    expect(chunkLocation({ page_start: 3, page_end: 5, heading_path: ["A"] })).toBe("Pages 3–5");
  });

  it("falls back to the heading trail", () => {
    expect(chunkLocation({ page_start: null, page_end: null, heading_path: ["Guide", "Setup"] })).toBe(
      "Guide › Setup",
    );
    expect(chunkLocation({ page_start: null, page_end: null, heading_path: [] })).toBeNull();
  });
});

describe("typeLabel", () => {
  it("labels by kind and MIME type", () => {
    expect(typeLabel({ kind: "note", mime_type: "text/markdown" })).toBe("Note");
    expect(typeLabel({ kind: "file", mime_type: "text/markdown" })).toBe("Markdown");
    expect(
      typeLabel({
        kind: "file",
        mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    ).toBe("Word");
  });
});
