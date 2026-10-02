import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { searchUrl } from "@/features/search/search-page";
import { SearchView, type SearchViewProps } from "@/features/search/search-view";
import type { SearchResponse, SearchResult } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function result(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    chunk_id: "k1",
    document_id: "d1",
    document_title: "Incident report",
    document_kind: "file",
    ordinal: 3,
    content: "The importer stopped with error ERR_4711 after a timeout.",
    page_start: 2,
    page_end: 3,
    heading_path: [],
    score: 0.0328,
    similarity: 0.571,
    vector_rank: 1,
    fulltext_rank: 1,
    ...overrides,
  };
}

function response(results: SearchResult[], mode: SearchResponse["mode"] = "hybrid"): SearchResponse {
  return { query: "ERR_4711", mode, embedding_model: "BAAI/bge-m3:int8@4de1325", results };
}

function renderView(props: Partial<SearchViewProps> = {}) {
  const onSearch = vi.fn();
  render(
    <SearchView query="" mode="hybrid" collections={[]} onSearch={onSearch} {...props} />,
  );
  return onSearch;
}

describe("SearchView", () => {
  it("shows tips before the first search", () => {
    renderView();
    expect(screen.getByText("Search tips")).toBeInTheDocument();
  });

  it("submits the trimmed query with the current mode", async () => {
    const onSearch = renderView({ mode: "fulltext" });
    await userEvent.type(screen.getByLabelText("Search query"), "  ERR_4711  {enter}");
    expect(onSearch).toHaveBeenCalledWith({ query: "ERR_4711", mode: "fulltext", collectionId: undefined });
  });

  it("re-runs the search when the mode changes", async () => {
    const onSearch = renderView({ query: "ERR_4711", response: response([result()]) });
    await userEvent.click(screen.getByRole("radio", { name: "Exact words" }));
    expect(onSearch).toHaveBeenCalledWith({ query: "ERR_4711", mode: "fulltext", collectionId: undefined });
  });

  it("renders results with location, highlights and how they matched", () => {
    renderView({
      query: "ERR_4711 timeout",
      response: response([
        result(),
        result({
          chunk_id: "k2",
          document_id: "d2",
          document_title: "Ops notes",
          document_kind: "note",
          ordinal: 0,
          page_start: null,
          page_end: null,
          heading_path: ["Runbook", "Timeouts"],
          similarity: null,
          vector_rank: null,
        }),
      ]),
    });
    const items = within(screen.getByRole("region", { name: "Search results" })).getAllByRole(
      "listitem",
    );
    expect(items).toHaveLength(2);

    const first = within(items[0]);
    expect(first.getByRole("link", { name: "Incident report" })).toHaveAttribute(
      "href",
      "/library/d1#chunk-3",
    );
    expect(first.getByText("Document · Pages 2–3")).toBeInTheDocument();
    expect(first.getAllByText(/ERR_4711|timeout/, { selector: "mark" })).toHaveLength(2);
    expect(first.getByText("Exact words")).toBeInTheDocument();
    expect(first.getByText("Meaning")).toBeInTheDocument();
    expect(first.getByText("57% similar")).toBeInTheDocument();

    const second = within(items[1]);
    expect(second.getByText("Note · Runbook › Timeouts")).toBeInTheDocument();
    expect(second.queryByText("Meaning")).not.toBeInTheDocument();
    expect(second.queryByText(/% similar/)).not.toBeInTheDocument();
  });

  it("explains an empty keyword search", () => {
    renderView({ query: "zzz", response: response([], "fulltext") });
    expect(screen.getByText("No passages found")).toBeInTheDocument();
    expect(screen.getByText(/Try “Best match”/)).toBeInTheDocument();
  });

  it("warns when the first search is slow", () => {
    renderView({ query: "x", loading: true, slow: true });
    expect(screen.getByText(/loads the language model/)).toBeInTheDocument();
  });

  it("shows errors", () => {
    renderView({ query: "x", error: "Authentication required" });
    expect(screen.getByRole("alert")).toHaveTextContent("Authentication required");
  });
});

describe("searchUrl", () => {
  it("keeps the URL short for defaults", () => {
    expect(searchUrl({ query: "ERR_4711", mode: "hybrid" })).toBe("/search?q=ERR_4711");
  });

  it("encodes mode, collection and special characters", () => {
    expect(searchUrl({ query: '"a b" & c', mode: "fulltext", collectionId: "c1" })).toBe(
      "/search?q=%22a+b%22+%26+c&mode=fulltext&collection=c1",
    );
  });
});
