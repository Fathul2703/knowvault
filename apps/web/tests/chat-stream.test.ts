import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { citedInText } from "@/features/chat/citations";
import { SseParser } from "@/features/chat/sse";
import {
  REFUSAL_TEXT,
  applyEvent,
  startTurn,
  streamAnswer,
  type AnswerEvent,
  type StreamSource,
} from "@/features/chat/stream";
import { ApiError } from "@/lib/api/client";

describe("SseParser", () => {
  it("joins messages split across chunks", () => {
    const parser = new SseParser();
    expect(parser.push('event: token\ndata: {"te')).toEqual([]);
    expect(parser.push('xt":"Hi"}\n\nevent: done\n')).toEqual([
      { event: "token", data: '{"text":"Hi"}' },
    ]);
    expect(parser.push("data: {}\n\n")).toEqual([{ event: "done", data: "{}" }]);
  });

  it("handles CRLF, comments, multi-line data and a missing final blank line", () => {
    const parser = new SseParser();
    expect(parser.push(": keep-alive\r\n\r\ndata: a\r\ndata: b\r\n\r\nevent: x\ndata: last")).toEqual([
      { event: "message", data: "a\nb" },
    ]);
    expect(parser.flush()).toEqual([{ event: "x", data: "last" }]);
    expect(parser.flush()).toEqual([]);
  });
});

const source: StreamSource = {
  ordinal: 1,
  chunk_id: "c1",
  chunk_ordinal: 4,
  document_id: "d1",
  title: "Leave policy",
  page_start: null,
  page_end: null,
  heading_path: ["Leave"],
  quoted_text: "Twelve days.",
};

function play(events: AnswerEvent[]) {
  return events.reduce(applyEvent, startTurn("How many days?"));
}

describe("applyEvent", () => {
  it("builds a complete answer with its cited sources", () => {
    const turn = play([
      { type: "message.created", conversation_id: "k", user_message_id: "u1", message_id: "m1" },
      { type: "sources", sources: [source, { ...source, ordinal: 2, chunk_id: "c2" }] },
      { type: "token", text: "Twelve days " },
      { type: "token", text: "[1]." },
      {
        type: "done",
        message_id: "m1",
        status: "complete",
        citations: [1],
        invalid_citations: [],
        usage: { input_tokens: 10, output_tokens: 3 },
      },
    ]);
    expect(turn).toMatchObject({
      userMessageId: "u1",
      messageId: "m1",
      status: "complete",
      content: "Twelve days [1].",
    });
    expect(turn.citations.map((c) => [c.ordinal, c.cited, c.document_title, c.chunk_ordinal])).toEqual([
      [1, true, "Leave policy", 4],
      [2, false, "Leave policy", 4],
    ]);
  });

  it("replaces streamed text with the refusal", () => {
    const turn = play([
      { type: "token", text: "I am not sure" },
      {
        type: "done",
        message_id: "m1",
        status: "refused",
        citations: [],
        invalid_citations: [],
        usage: { input_tokens: 1, output_tokens: 1 },
      },
    ]);
    expect(turn.status).toBe("refused");
    expect(turn.content).toBe(REFUSAL_TEXT);
  });

  it("keeps partial text on errors", () => {
    const turn = play([
      { type: "token", text: "Twelve" },
      { type: "error", message_id: "m1", code: "llm_timeout", detail: "Too slow." },
    ]);
    expect(turn).toMatchObject({ status: "error", content: "Twelve", errorCode: "llm_timeout" });
  });
});

describe("citedInText", () => {
  it("collects every marker", () => {
    expect(citedInText("A [2]. B [1, 3][2]. Not [x].")).toEqual([1, 2, 3]);
  });
});

function sseBody(text: string, chunkSize: number): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunkSize) {
        controller.enqueue(bytes.slice(i, i + chunkSize));
      }
      controller.close();
    },
  });
}

describe("streamAnswer", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => vi.stubGlobal("fetch", fetchMock));
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("posts the question and decodes events across chunk and UTF-8 boundaries", async () => {
    const text =
      'event: message.created\ndata: {"conversation_id":"k","user_message_id":"u","message_id":"m"}\n\n' +
      'event: token\ndata: {"text":"Dua belas hari — cuti"}\n\n' +
      "event: unknown\ndata: {}\n\n" +
      'event: done\ndata: {"message_id":"m","status":"complete","citations":[],"invalid_citations":[],"usage":{"input_tokens":1,"output_tokens":1}}\n\n';
    fetchMock.mockResolvedValue(
      new Response(sseBody(text, 7), { headers: { "Content-Type": "text/event-stream" } }),
    );
    const events: AnswerEvent[] = [];

    await streamAnswer("k 1", "Berapa hari?", { onEvent: (e) => events.push(e) });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/conversations\/k%201\/messages$/);
    expect(init).toMatchObject({ method: "POST", body: '{"content":"Berapa hari?"}' });
    expect(events.map((e) => e.type)).toEqual(["message.created", "token", "done"]);
    expect(events[1]).toEqual({ type: "token", text: "Dua belas hari — cuti" });
  });

  it("throws the problem of a request refused before streaming", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          type: "about:blank",
          title: "Daily token quota used up",
          status: 429,
          code: "token_quota_exceeded",
          detail: "You have used today's token quota for questions.",
        }),
        { status: 429, headers: { "Content-Type": "application/problem+json" } },
      ),
    );
    const error = await streamAnswer("k", "q", { onEvent: () => {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).problem?.code).toBe("token_quota_exceeded");
  });
});
