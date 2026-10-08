import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EntityView, groupByDocument } from "@/features/graph/entity-view";
import type { Entity, EntityMention } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function mention(overrides: Partial<EntityMention> = {}): EntityMention {
  return {
    document_id: "d1",
    document_title: "Supplier contract",
    chunk_ordinal: 0,
    snippet: "The Master Services Agreement governs every order.",
    count: 1,
    ...overrides,
  };
}

const entity: Entity = {
  id: "e1",
  name: "Master Services Agreement",
  type: "name",
  mentions: [
    mention(),
    mention({ chunk_ordinal: 4, snippet: "…under the master services agreements of 2024…", count: 2 }),
    mention({ document_id: "d2", document_title: "Renewal memo", chunk_ordinal: 1 }),
  ],
  neighbours: [{ id: "e2", name: "ERR_4711", type: "code", weight: 3 }],
  aliases: [{ name: "MSA", similarity: 0.91 }],
};

describe("EntityView", () => {
  it("shows the entity, how often it occurs and its aliases", () => {
    render(<EntityView entity={entity} />);
    expect(screen.getByRole("heading", { name: "Master Services Agreement" })).toBeInTheDocument();
    expect(screen.getByText("In 3 passages of 2 documents")).toBeInTheDocument();
    const aliases = screen.getByRole("region", { name: "Also written as" });
    expect(within(aliases).getByText("MSA").closest("li")).toHaveAttribute(
      "title",
      "Merged because the names are 91% similar",
    );
    expect(screen.getByRole("link", { name: "Search for it" })).toHaveAttribute(
      "href",
      "/search?q=%22Master+Services+Agreement%22&mode=fulltext",
    );
  });

  it("links every passage to its place in the document and highlights the name", () => {
    render(<EntityView entity={entity} />);
    const mentions = screen.getByRole("region", { name: "Mentioned in" });
    expect(within(mentions).getByRole("link", { name: "Supplier contract" })).toHaveAttribute(
      "href",
      "/library/d1",
    );
    expect(within(mentions).getByRole("link", { name: "Open passage 5 · 2×" })).toHaveAttribute(
      "href",
      "/library/d1#chunk-4",
    );
    const marks = mentions.querySelectorAll("mark");
    expect([...marks].map((mark) => mark.textContent)).toEqual([
      "Master Services Agreement",
      "master services agreement",
      "Master Services Agreement",
    ]);
  });

  it("links related entities", () => {
    render(<EntityView entity={entity} />);
    const related = screen.getByRole("region", { name: "Related" });
    expect(within(related).getByRole("link", { name: "ERR_4711" })).toHaveAttribute(
      "href",
      "/graph/entities/e2",
    );
    expect(related).toHaveTextContent("Together in 3 passages");
  });

  it("shows loading and errors", () => {
    const { rerender } = render(<EntityView />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    rerender(<EntityView error="The entity does not exist." />);
    expect(screen.getByRole("alert")).toHaveTextContent("The entity does not exist.");
  });
});

describe("groupByDocument", () => {
  it("keeps the order of documents and passages", () => {
    const groups = groupByDocument(entity.mentions);
    expect(groups.map((group) => [group.title, group.mentions.map((m) => m.chunk_ordinal)])).toEqual([
      ["Supplier contract", [0, 4]],
      ["Renewal memo", [1]],
    ]);
  });
});
