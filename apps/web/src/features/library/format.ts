import type { Chunk, DocumentItem, DocumentStatus } from "@/lib/api/client";

export const STATUS_BADGE: Record<
  DocumentStatus,
  { label: string; tone: "neutral" | "info" | "success" | "danger" }
> = {
  pending: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

const TYPE_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
  "text/markdown": "Markdown",
  "text/plain": "Text",
};

export function typeLabel(document: Pick<DocumentItem, "kind" | "mime_type">): string {
  if (document.kind === "note") {
    return "Note";
  }
  return TYPE_LABELS[document.mime_type] ?? "File";
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

/** Where a chunk comes from: pages for PDFs, the heading trail for other formats. */
export function chunkLocation(
  chunk: Pick<Chunk, "page_start" | "page_end" | "heading_path">,
): string | null {
  if (chunk.page_start != null) {
    return chunk.page_end != null && chunk.page_end !== chunk.page_start
      ? `Pages ${chunk.page_start}–${chunk.page_end}`
      : `Page ${chunk.page_start}`;
  }
  return chunk.heading_path.length ? chunk.heading_path.join(" › ") : null;
}

export const ACCEPTED_UPLOAD_TYPES = ".pdf,.docx,.md,.markdown,.txt";

const dateFormat = new Intl.DateTimeFormat("en", { dateStyle: "medium" });
const dateTimeFormat = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}
