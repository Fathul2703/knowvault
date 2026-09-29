import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LibraryView, type LibraryViewProps } from "@/features/library/library-view";
import type { Collection, DocumentItem } from "@/lib/api/client";

function doc(overrides: Partial<DocumentItem>): DocumentItem {
  return {
    id: "d1",
    kind: "file",
    title: "Attention Is All You Need",
    status: "ready",
    mime_type: "application/pdf",
    original_filename: "attention.pdf",
    size_bytes: 1024,
    page_count: 15,
    collection_id: null,
    error_code: null,
    error_detail: null,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

const papers: Collection = {
  id: "c1",
  name: "Papers",
  description: null,
  document_count: 1,
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

function renderView(props: Partial<LibraryViewProps> = {}) {
  const handlers = { onFiltersChange: vi.fn(), onUpload: vi.fn() };
  render(<LibraryView items={[]} collections={[]} filters={{}} {...handlers} {...props} />);
  return handlers;
}

describe("LibraryView", () => {
  it("shows an empty state", () => {
    renderView();
    expect(screen.getByText("Your library is empty")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("lists documents with type, collection and status", () => {
    renderView({
      items: [
        doc({ collection_id: "c1" }),
        doc({ id: "d2", kind: "note", title: "Reading notes", mime_type: "text/markdown", status: "processing" }),
      ],
      collections: [papers],
    });
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByRole("link", { name: "Attention Is All You Need" })).toHaveAttribute(
      "href",
      "/library/d1",
    );
    expect(within(rows[1]).getByText("PDF")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Papers")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Ready")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Note")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Processing")).toBeInTheDocument();
  });

  it("changes the type and collection filters", async () => {
    const { onFiltersChange } = renderView({ collections: [papers] });
    await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(onFiltersChange).toHaveBeenLastCalledWith({ kind: "note" });
    await userEvent.selectOptions(screen.getByRole("combobox"), "c1");
    expect(onFiltersChange).toHaveBeenLastCalledWith({ collectionId: "c1" });
  });

  it("uploads the chosen file", async () => {
    const { onUpload } = renderView();
    const file = new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choose a file to upload"), file);
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("shows upload progress and errors", () => {
    renderView({ uploading: true, uploadError: "Upload a PDF, Word (.docx), Markdown (.md) or text (.txt) file." });
    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Upload a PDF");
  });

  it("offers to load more when there are more pages", async () => {
    const onLoadMore = vi.fn();
    renderView({ items: [doc({})], hasMore: true, onLoadMore });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(onLoadMore).toHaveBeenCalled();
  });
});
