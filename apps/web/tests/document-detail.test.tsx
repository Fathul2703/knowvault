import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentDetail, chunkOrdinalFromHash } from "@/features/library/document-detail";
import { uploadDocument } from "@/features/library/hooks";
import { ApiError, type DocumentItem } from "@/lib/api/client";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));

const baseDocument: DocumentItem = {
  id: "d1",
  kind: "file",
  title: "Scan",
  status: "failed",
  mime_type: "application/pdf",
  original_filename: "scan.pdf",
  size_bytes: 2048,
  page_count: null,
  collection_id: null,
  error_code: "no_extractable_text",
  error_detail: "No text could be extracted.",
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

/** Routes requests by method and path. */
function serve(routes: Record<string, () => Response>) {
  fetchMock.mockImplementation(async (input) => {
    const request = input as Request;
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const handler = routes[key];
    if (!handler) {
      throw new Error(`Unexpected request: ${key}`);
    }
    return handler();
  });
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DocumentDetail id="d1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.stubGlobal("fetch", fetchMock));
afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("DocumentDetail", () => {
  it("explains a failure and can queue the document again", async () => {
    let current: DocumentItem = baseDocument;
    serve({
      "GET /api/v1/documents/d1": () => json(200, current),
      "GET /api/v1/collections": () => json(200, []),
      "POST /api/v1/documents/d1/reprocess": () => {
        current = { ...baseDocument, status: "pending", error_code: null, error_detail: null };
        return json(202, current);
      },
    });
    renderDetail();

    expect(await screen.findByRole("alert")).toHaveTextContent("No text could be extracted.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Waiting to be processed…")).toBeInTheDocument();
  });

  it("shows extracted chunks with their location", async () => {
    serve({
      "GET /api/v1/documents/d1": () =>
        json(200, { ...baseDocument, status: "ready", page_count: 4, error_code: null, error_detail: null }),
      "GET /api/v1/collections": () => json(200, []),
      "GET /api/v1/documents/d1/chunks": () =>
        json(200, {
          total: 1,
          items: [
            {
              id: "k1",
              ordinal: 0,
              content: "Transformers rely on attention.",
              char_count: 31,
              page_start: 2,
              page_end: 3,
              heading_path: [],
            },
          ],
        }),
    });
    renderDetail();

    expect(await screen.findByText("Transformers rely on attention.")).toBeInTheDocument();
    expect(screen.getByText("Pages 2–3")).toBeInTheDocument();
    expect(screen.getByText("1 chunks")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute(
      "href",
      "/api/v1/documents/d1/file",
    );
  });

  it("reports a missing document", async () => {
    serve({
      "GET /api/v1/documents/d1": () =>
        json(404, { type: "about:blank", title: "Resource not found", status: 404, code: "not_found" }),
      "GET /api/v1/collections": () => json(200, []),
    });
    renderDetail();
    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist");
  });
});

describe("links to a chunk", () => {
  it("parses the chunk hash", () => {
    expect(chunkOrdinalFromHash("#chunk-12")).toBe(12);
    expect(chunkOrdinalFromHash("#chunk-x")).toBeNull();
    expect(chunkOrdinalFromHash("")).toBeNull();
  });

  it("loads further pages until the linked chunk is there, then scrolls to it", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    window.location.hash = "#chunk-1";
    const chunk = (ordinal: number) => ({
      id: `k${ordinal}`,
      ordinal,
      content: `Passage ${ordinal}`,
      char_count: 9,
      page_start: null,
      page_end: null,
      heading_path: [],
    });
    fetchMock.mockImplementation(async (input) => {
      const request = input as Request;
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/documents/d1") {
        return json(200, { ...baseDocument, status: "ready", error_code: null, error_detail: null });
      }
      if (url.pathname === "/api/v1/collections") {
        return json(200, []);
      }
      // One chunk per page: the target (ordinal 1) is on the second page.
      const offset = Number(url.searchParams.get("offset"));
      return json(200, { total: 2, items: [chunk(offset)] });
    });

    renderDetail();

    const target = await screen.findByText("Passage 1");
    expect(target.closest("[id='chunk-1']")).toHaveAttribute("aria-current", "location");
    await vi.waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
    window.location.hash = "";
  });
});

describe("uploadDocument", () => {
  it("sends the file as multipart form data", async () => {
    serve({ "POST /api/v1/documents": () => json(202, { ...baseDocument, status: "pending" }) });
    const file = new File(["# hi"], "notes.md", { type: "text/markdown" });

    const created = await uploadDocument(file, "c1");

    expect(created.status).toBe("pending");
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/api/v1/documents");
    const form = await request.formData();
    // The part's filename comes from the browser's File object; jsdom's File does not carry it
    // through Node's Request, so only the content is checked here.
    expect(await (form.get("file") as Blob).text()).toBe("# hi");
    expect(form.get("collection_id")).toBe("c1");
    expect(request.headers.get("content-type")).toMatch(/^multipart\/form-data; boundary=/);
  });

  it("surfaces the server's rejection", async () => {
    serve({
      "POST /api/v1/documents": () =>
        json(415, {
          type: "about:blank",
          title: "Unsupported file type",
          status: 415,
          code: "unsupported_file_type",
          detail: "Upload a PDF, Word (.docx), Markdown (.md) or text (.txt) file.",
        }),
    });
    const error = await uploadDocument(new File(["x"], "a.png")).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem?.code).toBe("unsupported_file_type");
  });
});
