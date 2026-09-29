import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { LibraryView } from "@/features/library/library-view";
import type { LibraryItem } from "@/features/library/types";

const items: LibraryItem[] = [
  {
    id: "1",
    title: "Attention Is All You Need.pdf",
    kind: "file",
    status: "ready",
    collection: "Papers",
    updatedAt: "2026-09-01T10:00:00Z",
  },
  {
    id: "2",
    title: "Reading notes",
    kind: "note",
    status: "processing",
    collection: null,
    updatedAt: "2026-09-02T10:00:00Z",
  },
];

describe("LibraryView", () => {
  it("shows an empty state when there are no items", () => {
    render(<LibraryView items={[]} />);
    expect(screen.getByText("Your library is empty")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("keeps upload disabled until Phase 2", () => {
    render(<LibraryView items={[]} />);
    expect(screen.getByRole("button", { name: "Upload document" })).toBeDisabled();
  });

  it("lists items with their status", () => {
    render(<LibraryView items={items} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2 items
    expect(screen.getByText("Attention Is All You Need.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("filters by type", async () => {
    render(<LibraryView items={items} />);
    await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Attention Is All You Need.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Reading notes")).toBeInTheDocument();
  });
});
