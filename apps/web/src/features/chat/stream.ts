import { ApiError, isProblem, type Citation } from "@/lib/api/client";

import { SseParser } from "./sse";

/** Shown instead of an answer when the documents do not contain it (matches the API). */
export const REFUSAL_TEXT = "I couldn't find enough information in your documents to answer that.";

export const MAX_QUESTION_CHARS = 2000;

/** A source as sent in the `sources` event, before the answer says which ones it cites. */
export type StreamSource = {
  ordinal: number;
  chunk_id: string;
  chunk_ordinal: number;
  document_id: string;
  title: string;
  page_start: number | null;
  page_end: number | null;
  heading_path: string[];
  quoted_text: string;
};

/** Events of POST /api/v1/conversations/{id}/messages (docs/ARCHITECTURE.md §8.3). */
export type AnswerEvent =
  | { type: "message.created"; conversation_id: string; user_message_id: string; message_id: string }
  | { type: "sources"; sources: StreamSource[] }
  | { type: "token"; text: string }
  | {
      type: "done";
      message_id: string;
      status: "complete" | "refused";
      citations: number[];
      invalid_citations: number[];
      usage: { input_tokens: number; output_tokens: number };
    }
  | { type: "error"; message_id: string; code: string; detail: string };

const EVENT_TYPES = new Set(["message.created", "sources", "token", "done", "error"]);

/** An answer being written, shaped like a stored message so both render the same way. */
export type PendingTurn = {
  question: string;
  userMessageId: string | null;
  messageId: string | null;
  status: "streaming" | "complete" | "refused" | "error";
  content: string;
  citations: Citation[];
  errorCode: string | null;
  errorDetail: string | null;
};

export function startTurn(question: string): PendingTurn {
  return {
    question,
    userMessageId: null,
    messageId: null,
    status: "streaming",
    content: "",
    citations: [],
    errorCode: null,
    errorDetail: null,
  };
}

function toCitation(source: StreamSource): Citation {
  return {
    ordinal: source.ordinal,
    cited: false,
    chunk_id: source.chunk_id,
    chunk_ordinal: source.chunk_ordinal,
    document_id: source.document_id,
    document_title: source.title,
    quoted_text: source.quoted_text,
    page_start: source.page_start,
    page_end: source.page_end,
    heading_path: source.heading_path,
  };
}

export function applyEvent(turn: PendingTurn, event: AnswerEvent): PendingTurn {
  switch (event.type) {
    case "message.created":
      return { ...turn, userMessageId: event.user_message_id, messageId: event.message_id };
    case "sources":
      return { ...turn, citations: event.sources.map(toCitation) };
    case "token":
      return { ...turn, content: turn.content + event.text };
    case "done": {
      const cited = new Set(event.citations);
      return {
        ...turn,
        status: event.status,
        // A refusal replaces whatever was written before the model gave up.
        content: event.status === "refused" ? REFUSAL_TEXT : turn.content,
        citations: turn.citations.map((c) => ({ ...c, cited: cited.has(c.ordinal) })),
      };
    }
    case "error":
      return { ...turn, status: "error", errorCode: event.code, errorDetail: event.detail };
  }
}

function parseEvent(name: string, data: string): AnswerEvent | null {
  if (!EVENT_TYPES.has(name)) {
    return null;
  }
  try {
    return { type: name, ...JSON.parse(data) } as AnswerEvent;
  } catch {
    return null;
  }
}

/**
 * Asks a question and calls `onEvent` for each event of the answer. Problems found before the
 * stream starts (unknown conversation, an answer already running, quota used up) are thrown as
 * ApiError. The request is a plain fetch: EventSource cannot send a POST body.
 */
export async function streamAnswer(
  conversationId: string,
  question: string,
  { signal, onEvent }: { signal?: AbortSignal; onEvent: (event: AnswerEvent) => void },
): Promise<void> {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const response = await globalThis.fetch(
    `${origin}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content: question }),
      credentials: "same-origin",
      signal,
    },
  );
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => undefined);
    throw new ApiError(response.status, isProblem(body) ? body : undefined);
  }
  if (!response.body) {
    throw new Error("The answer stream is empty.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  const emit = (messages: ReturnType<SseParser["push"]>) => {
    for (const message of messages) {
      const event = parseEvent(message.event, message.data);
      if (event) {
        onEvent(event);
      }
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    emit(parser.push(decoder.decode(value, { stream: true })));
  }
  emit(parser.push(decoder.decode()));
  emit(parser.flush());
}
