import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { neighbourhood } from "@/features/graph/graph-canvas";
import { graphUrl } from "@/features/graph/graph-page";
import { GraphView, type GraphViewProps } from "@/features/graph/graph-view";
import type { Graph } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const graph: Graph = {
  nodes: [
    { id: "e1", name: "Master Services Agreement", type: "name", mentions: 9, documents: 2 },
    { id: "e2", name: "ERR_4711", type: "code", mentions: 4, documents: 1 },
    { id: "e3", name: "Bekasi", type: "name", mentions: 1, documents: 1 },
  ],
  edges: [{ source: "e1", target: "e2", type: "co_occurs", weight: 3 }],
};

function renderView(props: Partial<GraphViewProps> = {}) {
  const handlers = { onScopeChange: vi.fn(), onOpen: vi.fn() };
  render(<GraphView scope={{}} collections={[]} graph={graph} {...handlers} {...props} />);
  return handlers;
}

describe("GraphView", () => {
  it("draws every entity as a link and lists them by mentions", () => {
    renderView();
    const picture = screen.getByRole("group", { name: "Entity graph" });
    expect(
      within(picture).getByRole("link", {
        name: "ERR_4711, code, 4 mentions in 1 document",
      }),
    ).toHaveAttribute("href", "/graph/entities/e2");

    const list = screen.getByRole("list", { name: "Entities" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => within(item).getByRole("link").textContent)).toEqual([
      "Master Services Agreement",
      "ERR_4711",
      "Bekasi",
    ]);
    expect(items[0]).toHaveTextContent("Name · 9 mentions · 2 documents");
    expect(screen.getByText(/3 entities · 1 relation/)).toBeInTheDocument();
  });

  it("opens an entity when its node is clicked", async () => {
    const { onOpen } = renderView();
    await userEvent.click(screen.getByRole("link", { name: /^Bekasi, name/ }));
    expect(onOpen).toHaveBeenCalledWith("e3");
  });

  it("hides and shows entity types", async () => {
    renderView();
    const codes = screen.getByRole("button", { name: "Codes" });
    expect(codes).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(codes);
    expect(codes).toHaveAttribute("aria-pressed", "false");
    const list = screen.getByRole("list", { name: "Entities" });
    expect(within(list).queryByText("ERR_4711")).not.toBeInTheDocument();
    expect(screen.getByText(/2 entities · 0 relations \(of 3\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Names" }));
    expect(screen.getByText("All entity types are hidden.")).toBeInTheDocument();
  });

  it("changes the collection", async () => {
    const { onScopeChange } = renderView({
      collections: [
        {
          id: "c1",
          name: "Contracts",
          description: null,
          document_count: 3,
          created_at: "2026-09-01T10:00:00Z",
          updated_at: "2026-09-01T10:00:00Z",
        },
      ],
    });
    await userEvent.selectOptions(screen.getByLabelText("Collection"), "c1");
    expect(onScopeChange).toHaveBeenCalledWith({ collectionId: "c1" });
  });

  it("names the document it is limited to and can go back to all documents", async () => {
    const { onScopeChange } = renderView({
      scope: { documentId: "d1" },
      documentTitle: "Supplier contract",
    });
    expect(screen.queryByLabelText("Collection")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Supplier contract" })).toHaveAttribute(
      "href",
      "/library/d1",
    );
    await userEvent.click(screen.getByRole("button", { name: "Show all documents" }));
    expect(onScopeChange).toHaveBeenCalledWith({});
  });

  it("explains an empty graph and shows errors", () => {
    const { unmount } = renderEmpty();
    expect(screen.getByText("No entities yet")).toBeInTheDocument();
    unmount();
    renderView({ graph: undefined, error: "The service is unavailable." });
    expect(screen.getByRole("alert")).toHaveTextContent("The service is unavailable.");
  });
});

function renderEmpty() {
  return render(
    <GraphView
      scope={{}}
      collections={[]}
      graph={{ nodes: [], edges: [] }}
      onScopeChange={vi.fn()}
      onOpen={vi.fn()}
    />,
  );
}

describe("neighbourhood", () => {
  it("is the entity and everything that shares a passage with it", () => {
    expect([...neighbourhood("e2", graph.edges)].sort()).toEqual(["e1", "e2"]);
    expect(neighbourhood(null, graph.edges).size).toBe(0);
  });
});

describe("graphUrl", () => {
  it("keeps the scope in the URL, the document taking precedence", () => {
    expect(graphUrl({})).toBe("/graph");
    expect(graphUrl({ collectionId: "c1" })).toBe("/graph?collection=c1");
    expect(graphUrl({ collectionId: "c1", documentId: "d1" })).toBe("/graph?document=d1");
  });
});
