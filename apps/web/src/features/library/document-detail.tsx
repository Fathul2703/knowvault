"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { Alert, Badge, Button, Card, buttonClass, inputClass } from "@/components/ui";
import { errorMessage, type Chunk, type DocumentItem } from "@/lib/api/client";

import {
  STATUS_BADGE,
  chunkLocation,
  formatBytes,
  formatDateTime,
  typeLabel,
} from "./format";
import {
  isProcessing,
  useChunks,
  useCollections,
  useDeleteDocument,
  useDocument,
  useReprocessDocument,
  useUpdateDocument,
} from "./hooks";

/** `#chunk-12` in the URL points at the chunk with ordinal 12 (links from search results). */
export function chunkOrdinalFromHash(hash: string): number | null {
  const match = /^#chunk-(\d+)$/.exec(hash);
  return match ? Number(match[1]) : null;
}

export function DocumentDetail({ id }: { id: string }) {
  const router = useRouter();
  const document = useDocument(id);
  const collections = useCollections();
  const update = useUpdateDocument(id);
  const reprocess = useReprocessDocument(id);
  const remove = useDeleteDocument();
  const ready = document.data?.status === "ready";
  const chunks = useChunks(id, ready);
  const collectionFieldId = useId();

  // When processing finishes, load the freshly extracted chunks.
  const previousStatus = useRef(document.data?.status);
  const { refetch } = chunks;
  useEffect(() => {
    const status = document.data?.status;
    if (previousStatus.current && previousStatus.current !== status && status === "ready") {
      void refetch();
    }
    previousStatus.current = status;
  }, [document.data?.status, refetch]);

  // Scroll to the chunk named in the URL hash, loading further pages of chunks until it
  // is there (chunks are fetched 50 at a time).
  const [targetOrdinal, setTargetOrdinal] = useState<number | null>(null);
  useEffect(() => {
    const read = () => setTargetOrdinal(chunkOrdinalFromHash(window.location.hash));
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  const loadedChunks = chunks.data?.pages.flatMap((page) => page.items) ?? [];
  const targetLoaded =
    targetOrdinal !== null && loadedChunks.some((chunk) => chunk.ordinal === targetOrdinal);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = chunks;
  const chunksLoaded = Boolean(chunks.data);
  useEffect(() => {
    if (targetOrdinal === null || !chunksLoaded) {
      return;
    }
    if (targetLoaded) {
      window.document
        .getElementById(`chunk-${targetOrdinal}`)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    } else if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  }, [targetOrdinal, targetLoaded, chunksLoaded, hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (document.isError) {
    return (
      <div className="space-y-4">
        <Link href="/library" className="text-sm text-brand-600 hover:underline">
          ← Library
        </Link>
        <Alert>
          {document.error.status === 404
            ? "This document does not exist or was deleted."
            : errorMessage(document.error)}
        </Alert>
      </div>
    );
  }
  if (!document.data) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  const doc = document.data;
  const actionError = update.error ?? reprocess.error ?? remove.error;

  return (
    <div className="space-y-6">
      <Link href="/library" className="text-sm text-brand-600 hover:underline">
        ← Library
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold tracking-tight">{doc.title}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {typeLabel(doc)} · {formatBytes(doc.size_bytes)}
            {doc.page_count != null ? ` · ${doc.page_count} pages` : ""} · added{" "}
            {formatDateTime(doc.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {doc.kind === "note" ? (
            <Link href={`/library/notes/${doc.id}/edit`} className={buttonClass("secondary")}>
              Edit note
            </Link>
          ) : (
            <a href={`/api/v1/documents/${doc.id}/file`} className={buttonClass("secondary")}>
              Download
            </a>
          )}
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete “${doc.title}”? This cannot be undone.`)) {
                remove.mutate(doc.id, { onSuccess: () => router.replace("/library") });
              }
            }}
          >
            Delete
          </Button>
        </div>
      </div>

      {actionError ? <Alert>{errorMessage(actionError)}</Alert> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <section aria-labelledby="extracted-heading" className="space-y-3">
          <h2 id="extracted-heading" className="font-medium">
            Extracted text
            {chunks.data ? (
              <span className="ml-2 text-sm font-normal text-slate-500">
                {chunks.data.pages[0]?.total ?? 0} chunks
              </span>
            ) : null}
          </h2>
          <ProcessingState
            document={doc}
            onReprocess={() => reprocess.mutate()}
            reprocessing={reprocess.isPending}
          />
          {ready ? (
            <>
              {loadedChunks.map((chunk) => (
                <ChunkCard
                  key={chunk.id}
                  chunk={chunk}
                  highlighted={chunk.ordinal === targetOrdinal}
                />
              ))}
              {chunks.hasNextPage ? (
                <Button
                  variant="secondary"
                  disabled={chunks.isFetchingNextPage}
                  onClick={() => chunks.fetchNextPage()}
                >
                  {chunks.isFetchingNextPage ? "Loading…" : "Show more"}
                </Button>
              ) : null}
            </>
          ) : null}
        </section>

        <aside>
          <Card className="space-y-4 text-sm">
            <div>
              <p className="text-slate-500">Status</p>
              <Badge tone={STATUS_BADGE[doc.status].tone}>{STATUS_BADGE[doc.status].label}</Badge>
            </div>
            <div className="space-y-1.5">
              <label htmlFor={collectionFieldId} className="block text-slate-500">
                Collection
              </label>
              <select
                id={collectionFieldId}
                className={inputClass}
                value={doc.collection_id ?? ""}
                disabled={update.isPending}
                onChange={(e) => update.mutate({ collection_id: e.target.value || null })}
              >
                <option value="">No collection</option>
                {collections.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            {doc.original_filename ? (
              <div>
                <p className="text-slate-500">Original file</p>
                <p className="break-all">{doc.original_filename}</p>
              </div>
            ) : null}
            <div>
              <p className="text-slate-500">Last updated</p>
              <p>{formatDateTime(doc.updated_at)}</p>
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function ProcessingState({
  document,
  onReprocess,
  reprocessing,
}: {
  document: DocumentItem;
  onReprocess: () => void;
  reprocessing: boolean;
}) {
  if (isProcessing(document)) {
    return (
      <Card className="text-sm text-slate-600">
        <p aria-live="polite">
          {document.status === "pending"
            ? "Waiting to be processed…"
            : "Extracting text and splitting it into chunks…"}
        </p>
      </Card>
    );
  }
  if (document.status === "failed") {
    return (
      <Card className="space-y-3 border-red-200 bg-red-50 text-sm text-red-900">
        <p role="alert">{document.error_detail ?? "Processing failed."}</p>
        <Button variant="secondary" disabled={reprocessing} onClick={onReprocess}>
          {reprocessing ? "Queuing…" : "Try again"}
        </Button>
      </Card>
    );
  }
  return null;
}

function ChunkCard({ chunk, highlighted }: { chunk: Chunk; highlighted: boolean }) {
  const location = chunkLocation(chunk);
  return (
    <div
      id={`chunk-${chunk.ordinal}`}
      aria-current={highlighted ? "location" : undefined}
      className={`scroll-mt-24 rounded-lg ${highlighted ? "ring-2 ring-amber-400" : ""}`}
    >
      <Card className="space-y-2 p-4">
        <p className="flex items-center gap-2 text-xs text-slate-500">
          <span className="font-medium text-slate-700">#{chunk.ordinal + 1}</span>
          {location ? <span>{location}</span> : null}
          <span className="ml-auto">{chunk.char_count.toLocaleString("en")} characters</span>
        </p>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{chunk.content}</p>
      </Card>
    </div>
  );
}
