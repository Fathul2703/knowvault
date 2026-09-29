"use client";

import Link from "next/link";
import { useId, useRef, type ChangeEvent } from "react";

import { Alert, Badge, Button, Card, buttonClass, inputClass } from "@/components/ui";
import type { Collection, DocumentItem, DocumentKind } from "@/lib/api/client";

import { ACCEPTED_UPLOAD_TYPES, STATUS_BADGE, formatDate, typeLabel } from "./format";
import type { DocumentFilters } from "./hooks";

const KIND_FILTERS: ReadonlyArray<{ value: DocumentKind | undefined; label: string }> = [
  { value: undefined, label: "All" },
  { value: "file", label: "Files" },
  { value: "note", label: "Notes" },
];

export type LibraryViewProps = {
  items: readonly DocumentItem[];
  collections: readonly Collection[];
  filters: DocumentFilters;
  onFiltersChange: (filters: DocumentFilters) => void;
  onUpload: (file: File) => void;
  uploading?: boolean;
  uploadError?: string | null;
  loading?: boolean;
  loadError?: string | null;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadMore?: () => void;
};

export function LibraryView({
  items,
  collections,
  filters,
  onFiltersChange,
  onUpload,
  uploading = false,
  uploadError,
  loading = false,
  loadError,
  hasMore = false,
  loadingMore = false,
  onLoadMore,
}: LibraryViewProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const collectionFilterId = useId();
  const collectionNames = new Map(collections.map((c) => [c.id, c.name]));
  const filtered = filters.kind !== undefined || filters.collectionId !== undefined;

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      onUpload(file);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
          <p className="mt-1 text-sm text-slate-500">
            Documents and notes KnowVault can search and cite.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/library/notes/new" className={buttonClass("secondary")}>
            New note
          </Link>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPTED_UPLOAD_TYPES}
            className="sr-only"
            aria-label="Choose a file to upload"
            onChange={handleFile}
          />
          <Button disabled={uploading} onClick={() => fileInput.current?.click()}>
            {uploading ? "Uploading…" : "Upload document"}
          </Button>
        </div>
      </div>

      {uploadError ? <Alert>{uploadError}</Alert> : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Filter by type" className="flex gap-1">
          {KIND_FILTERS.map((option) => (
            <button
              key={option.label}
              role="tab"
              type="button"
              aria-selected={filters.kind === option.value}
              onClick={() => onFiltersChange({ ...filters, kind: option.value })}
              className={`rounded-md px-3 py-1.5 text-sm ${
                filters.kind === option.value
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-200/60"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <label htmlFor={collectionFilterId}>Collection</label>
          <select
            id={collectionFilterId}
            className={`${inputClass} w-48`}
            value={filters.collectionId ?? ""}
            onChange={(e) =>
              onFiltersChange({ ...filters, collectionId: e.target.value || undefined })
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

      {loadError ? (
        <Alert>{loadError}</Alert>
      ) : loading ? (
        <Card className="py-14 text-center text-sm text-slate-500">Loading…</Card>
      ) : items.length === 0 ? (
        <EmptyLibrary filtered={filtered} />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-5 py-3 font-medium">Title</th>
                <th scope="col" className="px-5 py-3 font-medium">Type</th>
                <th scope="col" className="px-5 py-3 font-medium">Collection</th>
                <th scope="col" className="px-5 py-3 font-medium">Status</th>
                <th scope="col" className="px-5 py-3 font-medium">Added</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="px-5 py-3">
                    <Link
                      href={`/library/${item.id}`}
                      className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
                    >
                      {item.title}
                    </Link>
                  </td>
                  <td className="whitespace-nowrap px-5 py-3 text-slate-600">{typeLabel(item)}</td>
                  <td className="px-5 py-3 text-slate-600">
                    {(item.collection_id && collectionNames.get(item.collection_id)) ?? "—"}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3">
                    <Badge tone={STATUS_BADGE[item.status].tone}>
                      {STATUS_BADGE[item.status].label}
                    </Badge>
                  </td>
                  <td className="whitespace-nowrap px-5 py-3 text-slate-600">
                    <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {hasMore ? (
        <div className="text-center">
          <Button variant="secondary" disabled={loadingMore} onClick={onLoadMore}>
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function EmptyLibrary({ filtered }: { filtered: boolean }) {
  return (
    <Card className="py-14 text-center">
      <p className="font-medium text-slate-900">
        {filtered ? "Nothing matches these filters" : "Your library is empty"}
      </p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
        {filtered
          ? "Try another type or collection."
          : "Upload a PDF, Word, Markdown or text file, or write a note. KnowVault extracts the text so it can be searched and cited."}
      </p>
    </Card>
  );
}
