// Mirrors the planned `documents` resource (docs/ARCHITECTURE.md §7.3). Replace with the
// generated API type once the documents endpoints exist in Phase 2.

export type DocumentKind = "file" | "note";
export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export type LibraryItem = {
  id: string;
  title: string;
  kind: DocumentKind;
  status: DocumentStatus;
  collection: string | null;
  updatedAt: string;
};
