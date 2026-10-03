"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, cx } from "@/components/ui";
import { chunkLocation } from "@/features/library/format";
import type { Citation, MessageStatus } from "@/lib/api/client";

import { AnswerMarkdown } from "./answer-markdown";
import { citedInText, sourceNumbers } from "./citations";
import { REFUSAL_TEXT } from "./stream";

/** What an answer needs to be shown, whether stored or still streaming. */
export type AnswerView = {
  key: string;
  status: MessageStatus;
  content: string;
  citations: Citation[];
  errorCode: string | null;
  /** True while this page is receiving the answer. */
  live: boolean;
};

const ERROR_TEXT: Record<string, string> = {
  client_disconnected: "The answer stopped because the page was closed or the connection dropped.",
  connection_lost: "The connection was lost while the answer was being written.",
  llm_timeout: "The language model did not respond in time. Try asking again.",
  llm_rate_limited: "The language model is busy. Try again in a minute.",
  llm_unavailable: "The language model is unavailable right now. Try again later.",
};

export function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-slate-900 px-4 py-2.5 text-sm text-white">
        {content}
      </p>
    </div>
  );
}

function sourceAnchor(answerKey: string, ordinal: number): string {
  return `answer-${answerKey}-source-${ordinal}`;
}

export function AssistantMessage({ answer }: { answer: AnswerView }) {
  const [open, setOpen] = useState<number | null>(null);
  const streaming = answer.status === "streaming";
  const available = sourceNumbers(answer.citations);
  // While streaming, the answer's own markers say which sources it uses so far.
  const citedNumbers = new Set(
    streaming
      ? citedInText(answer.content)
      : answer.citations.filter((c) => c.cited).map((c) => c.ordinal),
  );
  const cited = answer.citations.filter((c) => citedNumbers.has(c.ordinal));
  const others = answer.citations.filter((c) => !citedNumbers.has(c.ordinal));

  function cite(ordinal: number) {
    setOpen(ordinal);
    document
      .getElementById(sourceAnchor(answer.key, ordinal))
      ?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  return (
    <article aria-label="Answer" aria-busy={streaming} className="space-y-3">
      {answer.status === "refused" ? (
        <div className="space-y-1.5 rounded-lg border border-slate-200 bg-white px-4 py-3">
          <Badge>Not in your documents</Badge>
          <p className="text-sm text-slate-600">{answer.content || REFUSAL_TEXT}</p>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          {answer.content ? (
            <AnswerMarkdown text={answer.content} sources={available} onCite={cite} />
          ) : streaming ? (
            <p className="text-sm text-slate-500" aria-live="polite">
              {answer.live
                ? answer.citations.length
                  ? "Writing the answer…"
                  : "Searching your documents…"
                : "This answer is still being written. Refresh in a moment."}
            </p>
          ) : null}
          {streaming && answer.content ? (
            <span aria-hidden className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-slate-400 align-middle" />
          ) : null}
          {answer.status === "complete" && cited.length === 0 ? (
            <p className="mt-2">
              <Badge tone="warning">Unverified: this answer cites no source</Badge>
            </p>
          ) : null}
        </div>
      )}

      {answer.status === "error" ? (
        <Alert>
          {ERROR_TEXT[answer.errorCode ?? ""] ?? "The answer could not be completed."}
        </Alert>
      ) : null}

      {cited.length ? (
        <SourceList
          label="Sources"
          answerKey={answer.key}
          citations={cited}
          open={open}
          onToggle={setOpen}
        />
      ) : null}
      {others.length && !streaming ? (
        <details className="text-sm text-slate-600">
          <summary className="cursor-pointer select-none text-xs text-slate-500">
            {cited.length ? "Other passages searched" : "Passages searched"} ({others.length})
          </summary>
          <SourceList
            label="Other passages"
            answerKey={answer.key}
            citations={others}
            open={open}
            onToggle={setOpen}
          />
        </details>
      ) : null}
    </article>
  );
}

function SourceList({
  label,
  answerKey,
  citations,
  open,
  onToggle,
}: {
  label: string;
  answerKey: string;
  citations: Citation[];
  open: number | null;
  onToggle: (ordinal: number | null) => void;
}) {
  return (
    <ol aria-label={label} className="mt-2 space-y-1.5">
      {citations.map((citation) => (
        <SourceItem
          key={citation.ordinal}
          id={sourceAnchor(answerKey, citation.ordinal)}
          citation={citation}
          expanded={open === citation.ordinal}
          onToggle={() => onToggle(open === citation.ordinal ? null : citation.ordinal)}
        />
      ))}
    </ol>
  );
}

export function sourceHref(citation: Citation): string | null {
  if (!citation.document_id) {
    return null;
  }
  return citation.chunk_ordinal != null
    ? `/library/${citation.document_id}#chunk-${citation.chunk_ordinal}`
    : `/library/${citation.document_id}`;
}

function SourceItem({
  id,
  citation,
  expanded,
  onToggle,
}: {
  id: string;
  citation: Citation;
  expanded: boolean;
  onToggle: () => void;
}) {
  const location = chunkLocation(citation);
  const href = sourceHref(citation);
  return (
    <li
      id={id}
      className={cx(
        "rounded-md border bg-white text-sm",
        expanded ? "border-brand-600/40 ring-2 ring-brand-600/10" : "border-slate-200",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-2">
        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded bg-brand-50 px-1 text-xs font-semibold text-brand-700">
          {citation.ordinal}
        </span>
        {href ? (
          <Link href={href} className="font-medium text-slate-900 hover:text-brand-700 hover:underline">
            {citation.document_title}
          </Link>
        ) : (
          <span className="font-medium text-slate-900">{citation.document_title}</span>
        )}
        {location ? <span className="text-xs text-slate-500">{location}</span> : null}
        {!citation.document_id ? (
          <Badge tone="danger">Document deleted</Badge>
        ) : !citation.chunk_id ? (
          <Badge tone="warning">Document changed since</Badge>
        ) : null}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="ml-auto text-xs font-medium text-slate-500 hover:text-slate-900"
        >
          {expanded ? "Hide passage" : "Show passage"}
        </button>
      </div>
      {expanded ? (
        <blockquote className="max-h-72 overflow-y-auto whitespace-pre-wrap border-t border-slate-100 px-3 py-2 text-slate-700">
          {citation.quoted_text}
        </blockquote>
      ) : null}
    </li>
  );
}
