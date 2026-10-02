"use client";

import Link from "next/link";
import { useId, useState, type FormEvent } from "react";

import { Alert, Badge, Button, Card, inputClass } from "@/components/ui";
import { chunkLocation } from "@/features/library/format";
import type {
  Collection,
  SearchMode,
  SearchResponse,
  SearchResult,
} from "@/lib/api/client";

import { highlightSegments, makeSnippet, queryTerms } from "./highlight";
import type { SearchParams } from "./hooks";

export const MODES: ReadonlyArray<{
  value: SearchMode;
  label: string;
  hint: string;
}> = [
  {
    value: "hybrid",
    label: "Best match",
    hint: "Meaning and exact words combined",
  },
  {
    value: "vector",
    label: "Meaning",
    hint: "Finds paraphrases, also across languages",
  },
  {
    value: "fulltext",
    label: "Exact words",
    hint: "Names, codes, quoted phrases",
  },
];

export type SearchViewProps = {
  query: string;
  mode: SearchMode;
  collectionId?: string;
  collections: readonly Collection[];
  onSearch: (params: SearchParams) => void;
  loading?: boolean;
  slow?: boolean;
  error?: string | null;
  response?: SearchResponse;
};

export function SearchView({
  query,
  mode,
  collectionId,
  collections,
  onSearch,
  loading = false,
  slow = false,
  error,
  response,
}: SearchViewProps) {
  const [draft, setDraft] = useState(query);
  const fieldId = useId();

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.trim()) {
      onSearch({ query: draft.trim(), mode, collectionId });
    }
  }

  // Changing a filter re-runs the current search right away.
  function refine(changes: Partial<SearchParams>) {
    onSearch({ query: draft.trim() || query, mode, collectionId, ...changes });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="mt-1 text-sm text-slate-500">
          Find passages in your documents and notes by meaning or by exact
          words.
        </p>
      </div>

      <form role="search" onSubmit={submit} className="space-y-3">
        <div className="flex gap-2">
          <label htmlFor={`${fieldId}-q`} className="sr-only">
            Search query
          </label>
          <input
            id={`${fieldId}-q`}
            type="search"
            className={inputClass}
            placeholder='e.g. how are citations stored?  or  "error ERR_4711"'
            value={draft}
            maxLength={2000}
            onChange={(e) => setDraft(e.target.value)}
          />
          <Button type="submit" disabled={!draft.trim() || loading}>
            Search
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <div
              role="radiogroup"
              aria-label="Search mode"
              className="flex gap-1"
            >
              {MODES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={mode === option.value}
                  aria-describedby={`${fieldId}-mode-hint`}
                  onClick={() => refine({ mode: option.value })}
                  className={`rounded-md px-3 py-1.5 text-sm ${
                    mode === option.value
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-200/60"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p id={`${fieldId}-mode-hint`} className="text-xs text-slate-500">
              {MODES.find((option) => option.value === mode)?.hint}
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <label htmlFor={`${fieldId}-collection`}>Collection</label>
            <select
              id={`${fieldId}-collection`}
              className={`${inputClass} w-48`}
              value={collectionId ?? ""}
              onChange={(e) =>
                refine({ collectionId: e.target.value || undefined })
              }
            >
              <option value="">All collections</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </form>

      <Results
        query={query}
        loading={loading}
        slow={slow}
        error={error}
        response={response}
      />
    </div>
  );
}

function Results({
  query,
  loading,
  slow,
  error,
  response,
}: Pick<SearchViewProps, "query" | "loading" | "slow" | "error" | "response">) {
  if (!query) {
    return (
      <Card className="space-y-2 text-sm text-slate-600">
        <p className="font-medium text-slate-900">Search tips</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            Ask in your own words, in Indonesian or English — documents in
            either language match.
          </li>
          <li>
            Use <code>&quot;quotes&quot;</code> for an exact phrase,{" "}
            <code>-word</code> to exclude a word and <code>OR</code> for
            alternatives.
          </li>
          <li>Only documents that finished processing are searched.</li>
        </ul>
      </Card>
    );
  }
  if (error) {
    return <Alert>{error}</Alert>;
  }
  if (loading || !response) {
    return (
      <Card className="text-sm text-slate-500">
        <p aria-live="polite">
          {slow
            ? "Still searching… The first search after a restart loads the language model and can take up to half a minute."
            : "Searching…"}
        </p>
      </Card>
    );
  }
  if (response.results.length === 0) {
    return (
      <Card className="py-10 text-center">
        <p className="font-medium text-slate-900">No passages found</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
          {response.mode === "fulltext"
            ? "No passage contains these words. Try “Best match” to search by meaning."
            : "Try other words, another collection, or check that your documents are ready."}
        </p>
      </Card>
    );
  }

  const terms = queryTerms(query);
  return (
    <section aria-label="Search results" className="space-y-3">
      <p className="text-sm text-slate-500">
        {response.results.length}{" "}
        {response.results.length === 1 ? "passage" : "passages"}
      </p>
      <ol className="space-y-3">
        {response.results.map((result) => (
          <li key={result.chunk_id}>
            <ResultCard result={result} terms={terms} />
          </li>
        ))}
      </ol>
    </section>
  );
}

function ResultCard({
  result,
  terms,
}: {
  result: SearchResult;
  terms: string[];
}) {
  const location = chunkLocation(result);
  const snippet = makeSnippet(result.content, terms);
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link
          href={`/library/${result.document_id}#chunk-${result.ordinal}`}
          className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
        >
          {result.document_title}
        </Link>
        <span className="text-xs text-slate-500">
          {result.document_kind === "note" ? "Note" : "Document"}
          {location ? ` · ${location}` : ""}
        </span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
        {snippet.clippedStart ? "… " : ""}
        {highlightSegments(snippet.text, terms).map((segment, index) =>
          segment.match ? (
            <mark
              key={index}
              className="rounded bg-amber-100 px-0.5 text-slate-900"
            >
              {segment.text}
            </mark>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
        {snippet.clippedEnd ? " …" : ""}
      </p>
      <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {result.fulltext_rank != null ? (
          <Badge tone="info">Exact words</Badge>
        ) : null}
        {result.vector_rank != null ? (
          <Badge tone="success">Meaning</Badge>
        ) : null}
        {result.similarity != null ? (
          <span title="Cosine similarity between the passage and your query">
            {Math.round(result.similarity * 100)}% similar
          </span>
        ) : null}
      </p>
    </Card>
  );
}
