import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPage } from "@/features/chat/chat-page";
import { REFUSAL_TEXT } from "@/features/chat/stream";
import type { Citation, ConversationDetail, Message } from "@/lib/api/client";

const push = vi.fn();
let pathname = "/chat";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => pathname,
}));

const fetchMock = vi.fn<typeof fetch>();
type Handler = (body: unknown) => Response | Promise<Response>;

/** Routes requests from openapi-fetch (a Request) and from plain fetch (URL and init). */
function serve(routes: Record<string, Handler>) {
  fetchMock.mockImplementation(async (input, init) => {
    const request = input instanceof Request ? input : new Request(String(input), init);
    const key = `${request.method} ${new URL(request.url).pathname}`;
    const handler = routes[key];
    if (!handler) {
      throw new Error(`Unexpected request: ${key}`);
    }
    const text = request.method === "GET" || request.method === "DELETE" ? "" : await request.text();
    return handler(text ? JSON.parse(text) : undefined);
  });
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

function sse(events: Array<[string, unknown]>) {
  const text = events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(text, { headers: { "Content-Type": "text/event-stream" } });
}

const NOW = "2026-10-03T10:00:00Z";

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    ordinal: 1,
    cited: true,
    chunk_id: "c1",
    chunk_ordinal: 3,
    document_id: "d1",
    document_title: "Leave policy",
    quoted_text: "Employees get twelve days of annual leave.",
    page_start: null,
    page_end: null,
    heading_path: ["Annual leave"],
    ...overrides,
  };
}

function message(overrides: Partial<Message>): Message {
  return {
    id: "m",
    role: "assistant",
    content: "",
    status: "complete",
    model_id: "fake-extractive",
    error_code: null,
    created_at: NOW,
    citations: [],
    ...overrides,
  };
}

function conversation(messages: Message[], title = "Leave"): ConversationDetail {
  return {
    id: "k1",
    title,
    scope: { collection_id: null, document_ids: [] },
    created_at: NOW,
    updated_at: NOW,
    messages,
  };
}

const listOf = (items: ConversationDetail[]) => () =>
  json(200, {
    items: items.map((c) => ({
      id: c.id,
      title: c.title,
      scope: c.scope,
      created_at: c.created_at,
      updated_at: c.updated_at,
    })),
    next_cursor: null,
  });

function renderChat(conversationId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ChatPage conversationId={conversationId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  pathname = "/chat";
});
afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
});

describe("stored conversation", () => {
  const stored = conversation([
    message({ id: "u1", role: "user", content: "How many days of leave?" }),
    message({
      id: "a1",
      content: "Twelve days [1].",
      citations: [citation(), citation({ ordinal: 2, cited: false, document_title: "Recipes" })],
    }),
    message({ id: "u2", role: "user", content: "Who won the match?" }),
    message({ id: "a2", status: "refused", content: REFUSAL_TEXT, model_id: null }),
    message({ id: "u3", role: "user", content: "And holidays?" }),
    message({ id: "a3", status: "error", content: "Holidays", error_code: "llm_timeout" }),
    message({ id: "u4", role: "user", content: "Summarise" }),
    message({
      id: "a4",
      content: "A summary without markers.",
      citations: [citation({ cited: false, chunk_id: null, chunk_ordinal: null, document_id: null })],
    }),
  ]);

  beforeEach(() => {
    pathname = "/chat/k1";
    serve({
      "GET /api/v1/conversations": listOf([stored]),
      "GET /api/v1/conversations/k1": () => json(200, stored),
      "GET /api/v1/collections": () => json(200, []),
    });
  });

  it("shows answers, refusals, failures and unverified answers", async () => {
    renderChat("k1");
    const answers = await screen.findAllByRole("article", { name: "Answer" });
    expect(answers).toHaveLength(4);

    const [answered, refused, failed, unverified] = answers;
    expect(within(answered).getByRole("list", { name: "Sources" })).toHaveTextContent("Leave policy");
    expect(within(answered).getByText(/Other passages searched \(1\)/)).toBeInTheDocument();
    expect(within(refused).getByText("Not in your documents")).toBeInTheDocument();
    expect(within(refused).getByText(REFUSAL_TEXT)).toBeInTheDocument();
    expect(within(failed).getByRole("alert")).toHaveTextContent("did not respond in time");
    expect(within(failed).getByText("Holidays")).toBeInTheDocument();
    expect(within(unverified).getByText(/Unverified/)).toBeInTheDocument();
    expect(screen.getByText("Answers use: All documents")).toBeInTheDocument();
  });

  it("opens the cited passage and links to the exact chunk", async () => {
    renderChat("k1");
    const [answered] = await screen.findAllByRole("article", { name: "Answer" });

    await userEvent.click(within(answered).getByRole("button", { name: "Show source 1" }));

    const sources = within(answered).getByRole("list", { name: "Sources" });
    expect(within(sources).getByText("Employees get twelve days of annual leave.")).toBeInTheDocument();
    expect(within(sources).getByRole("link", { name: "Leave policy" })).toHaveAttribute(
      "href",
      "/library/d1#chunk-3",
    );
  });

  it("marks sources whose document was deleted", async () => {
    renderChat("k1");
    const answers = await screen.findAllByRole("article", { name: "Answer" });
    await userEvent.click(within(answers[3]).getByText(/Passages searched/));
    expect(within(answers[3]).getByText("Document deleted")).toBeInTheDocument();
    expect(within(answers[3]).queryByRole("link", { name: "Leave policy" })).toBeNull();
  });

  it("deletes the conversation after confirmation", async () => {
    let deleted = false;
    serve({
      "GET /api/v1/conversations": listOf([stored]),
      "GET /api/v1/conversations/k1": () => json(200, stored),
      "GET /api/v1/collections": () => json(200, []),
      "DELETE /api/v1/conversations/k1": () => {
        deleted = true;
        return new Response(null, { status: 204 });
      },
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderChat("k1");

    await userEvent.click(await screen.findByRole("button", { name: "Delete" }));

    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/chat"));
    expect(deleted).toBe(true);
  });
});

describe("new conversation", () => {
  it("creates the conversation, streams the answer and keeps it after reload", async () => {
    const replaceState = vi.spyOn(window.history, "replaceState");
    const created: unknown[] = [];
    let saved: ConversationDetail = conversation([], "");
    serve({
      "GET /api/v1/conversations": listOf([]),
      "GET /api/v1/collections": () => json(200, [{ id: "col1", name: "HR", description: null, document_count: 1, created_at: NOW, updated_at: NOW }]),
      "POST /api/v1/conversations": (body) => {
        created.push(body);
        return json(201, { ...conversation([], ""), messages: undefined });
      },
      "GET /api/v1/conversations/k1": () => json(200, saved),
      "POST /api/v1/conversations/k1/messages": (body) => {
        expect(body).toEqual({ content: "How many days of leave?" });
        saved = conversation(
          [
            message({ id: "u1", role: "user", content: "How many days of leave?" }),
            message({ id: "a1", content: "Twelve days [1].", citations: [citation()] }),
          ],
          "How many days of leave?",
        );
        return sse([
          ["message.created", { conversation_id: "k1", user_message_id: "u1", message_id: "a1" }],
          [
            "sources",
            {
              sources: [
                {
                  ordinal: 1,
                  chunk_id: "c1",
                  chunk_ordinal: 3,
                  document_id: "d1",
                  title: "Leave policy",
                  page_start: null,
                  page_end: null,
                  heading_path: ["Annual leave"],
                  quoted_text: "Employees get twelve days of annual leave.",
                },
              ],
            },
          ],
          ["token", { text: "Twelve days " }],
          ["token", { text: "[1]." }],
          [
            "done",
            {
              message_id: "a1",
              status: "complete",
              citations: [1],
              invalid_citations: [],
              usage: { input_tokens: 5, output_tokens: 3 },
            },
          ],
        ]);
      },
    });
    renderChat();

    await screen.findByRole("option", { name: "HR" });
    await userEvent.selectOptions(screen.getByLabelText("Search in"), "col1");
    await userEvent.type(screen.getByLabelText("Your question"), "How many days of leave?{Enter}");

    const answer = await screen.findByRole("article", { name: "Answer" });
    await within(answer).findByRole("button", { name: "Show source 1" });
    expect(answer).toHaveTextContent("Twelve days");
    expect(created).toEqual([{ title: "", scope: { collection_id: "col1", document_ids: [] } }]);
    expect(replaceState).toHaveBeenCalledWith(null, "", "/chat/k1");
    expect(screen.getAllByText("How many days of leave?").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Your question")).toHaveValue("");
    // After the stream, the stored conversation replaces the live answer without duplicates.
    await vi.waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("How many days of leave?"),
    );
    expect(screen.getAllByRole("article", { name: "Answer" })).toHaveLength(1);
  });

  it("shows the turn once when the conversation loads before the stream starts", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        controller = c;
      },
    });
    const send = (name: string, data: unknown) =>
      controller.enqueue(new TextEncoder().encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
    let finished = false;
    serve({
      "GET /api/v1/conversations": listOf([]),
      "GET /api/v1/collections": () => json(200, []),
      "POST /api/v1/conversations": () => json(201, { ...conversation([], ""), messages: undefined }),
      "GET /api/v1/conversations/k1": () =>
        json(
          200,
          conversation([
            message({ id: "u1", role: "user", content: "Q?" }),
            finished
              ? message({ id: "a1", content: "Done." })
              : message({ id: "a1", status: "streaming", model_id: null }),
          ]),
        ),
      "POST /api/v1/conversations/k1/messages": () =>
        new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    });
    renderChat();

    await userEvent.type(await screen.findByLabelText("Your question"), "Q?{Enter}");
    await screen.findByText("Searching your documents…");
    await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(5));
    expect(screen.getAllByText("Q?")).toHaveLength(1);
    expect(screen.getAllByRole("article", { name: "Answer" })).toHaveLength(1);

    send("message.created", { conversation_id: "k1", user_message_id: "u1", message_id: "a1" });
    send("sources", { sources: [] });
    send("token", { text: "Done." });
    finished = true;
    send("done", {
      message_id: "a1",
      status: "complete",
      citations: [],
      invalid_citations: [],
      usage: { input_tokens: 1, output_tokens: 1 },
    });
    controller.close();

    await vi.waitFor(() => expect(screen.getByText("Done.")).toBeInTheDocument());
    expect(screen.getAllByText("Q?")).toHaveLength(1);
    expect(screen.getAllByRole("article", { name: "Answer" })).toHaveLength(1);
  });

  it("puts the question back when it is refused before streaming", async () => {
    serve({
      "GET /api/v1/conversations": listOf([]),
      "GET /api/v1/collections": () => json(200, []),
      "POST /api/v1/conversations": () => json(201, { ...conversation([], ""), messages: undefined }),
      "GET /api/v1/conversations/k1": () => json(200, conversation([], "")),
      "POST /api/v1/conversations/k1/messages": () =>
        json(429, {
          type: "about:blank",
          title: "Daily token quota used up",
          status: 429,
          code: "token_quota_exceeded",
          detail: "You have used today's token quota for questions.",
        }),
    });
    renderChat();

    await userEvent.type(await screen.findByLabelText("Your question"), "Anything?{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("today's token quota");
    expect(screen.getByLabelText("Your question")).toHaveValue("Anything?");
    expect(screen.queryByRole("article", { name: "Answer" })).toBeNull();
  });

  it("does not send on Shift+Enter or an empty question", async () => {
    serve({
      "GET /api/v1/conversations": listOf([]),
      "GET /api/v1/collections": () => json(200, []),
    });
    renderChat();
    const field = await screen.findByLabelText("Your question");

    await userEvent.type(field, "   {Enter}");
    await userEvent.type(field, "line one{Shift>}{Enter}{/Shift}line two");

    expect(field).toHaveValue("   line one\nline two");
    expect(fetchMock.mock.calls.every(([input]) => (input as Request).method === "GET")).toBe(true);
  });
});
