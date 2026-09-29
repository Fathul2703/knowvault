"use client";

import { useMemo, useState } from "react";

import { Badge, Button, Card } from "@/components/ui";

import type { DocumentKind, DocumentStatus, LibraryItem } from "./types";

type KindFilter = "all" | DocumentKind;

const FILTERS: ReadonlyArray<{ value: KindFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "file", label: "Files" },
  { value: "note", label: "Notes" },
];

const STATUS_BADGE: Record<DocumentStatus, { label: string; tone: "neutral" | "info" | "success" | "danger" }> = {
  pending: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

const dateFormat = new Intl.DateTimeFormat("en", { dateStyle: "medium" });

export function LibraryView({ items }: { items: readonly LibraryItem[] }) {
  const [filter, setFilter] = useState<KindFilter>("all");
  const visible = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.kind === filter)),
    [items, filter],
  );

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
          <Button variant="secondary" disabled title="Available in Phase 2">
            New note
          </Button>
          <Button disabled title="Available in Phase 2">
            Upload document
          </Button>
        </div>
      </div>

      <div role="tablist" aria-label="Filter by type" className="flex gap-1">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            role="tab"
            type="button"
            aria-selected={filter === option.value}
            onClick={() => setFilter(option.value)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              filter === option.value
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-200/60"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <EmptyLibrary filtered={items.length > 0} />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-5 py-3 font-medium">Title</th>
                <th scope="col" className="px-5 py-3 font-medium">Type</th>
                <th scope="col" className="px-5 py-3 font-medium">Collection</th>
                <th scope="col" className="px-5 py-3 font-medium">Status</th>
                <th scope="col" className="px-5 py-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {visible.map((item) => (
                <tr key={item.id}>
                  <td className="px-5 py-3 font-medium text-slate-900">{item.title}</td>
                  <td className="px-5 py-3 text-slate-600">{item.kind === "file" ? "File" : "Note"}</td>
                  <td className="px-5 py-3 text-slate-600">{item.collection ?? "—"}</td>
                  <td className="px-5 py-3">
                    <Badge tone={STATUS_BADGE[item.status].tone}>{STATUS_BADGE[item.status].label}</Badge>
                  </td>
                  <td className="px-5 py-3 text-slate-600">
                    <time dateTime={item.updatedAt}>{dateFormat.format(new Date(item.updatedAt))}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function EmptyLibrary({ filtered }: { filtered: boolean }) {
  return (
    <Card className="py-14 text-center">
      <p className="font-medium text-slate-900">
        {filtered ? "Nothing matches this filter" : "Your library is empty"}
      </p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
        {filtered
          ? "Try another type."
          : "Uploading documents and writing notes arrive in Phase 2. Everything you add will be searchable and citable."}
      </p>
    </Card>
  );
}
