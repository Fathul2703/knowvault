"use client";

import Link from "next/link";
import { useId, useMemo, useState } from "react";

import { Alert, Card, cx, inputClass } from "@/components/ui";
import type { Collection, Graph } from "@/lib/api/client";

import { entityPath, entityType, plural } from "./entity-types";
import { GraphCanvas } from "./graph-canvas";
import type { GraphScope } from "./hooks";

export type GraphViewProps = {
  scope: GraphScope;
  /** Title of the document the graph is limited to, once it is known. */
  documentTitle?: string;
  collections: readonly Collection[];
  onScopeChange: (scope: GraphScope) => void;
  onOpen: (id: string) => void;
  loading?: boolean;
  error?: string | null;
  graph?: Graph;
};

export function GraphView({
  scope,
  documentTitle,
  collections,
  onScopeChange,
  onOpen,
  loading = false,
  error,
  graph,
}: GraphViewProps) {
  const fieldId = useId();
  const [active, setActive] = useState<string | null>(null);
  const [hiddenTypes, setHiddenTypes] = useState<ReadonlySet<string>>(new Set());

  const types = useMemo(
    () => [...new Set((graph?.nodes ?? []).map((node) => node.type))].sort(),
    [graph],
  );
  const nodes = useMemo(
    () => (graph?.nodes ?? []).filter((node) => !hiddenTypes.has(node.type)),
    [graph, hiddenTypes],
  );
  const edges = useMemo(() => {
    const shown = new Set(nodes.map((node) => node.id));
    return (graph?.edges ?? []).filter((edge) => shown.has(edge.source) && shown.has(edge.target));
  }, [graph, nodes]);

  function toggleType(type: string) {
    setActive(null);
    setHiddenTypes((current) => {
      const next = new Set(current);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Graph</h1>
          <p className="mt-1 text-sm text-slate-500">
            Names and codes found in your documents, linked when they appear in the same passage.
          </p>
        </div>
        {scope.documentId ? null : (
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <label htmlFor={`${fieldId}-collection`}>Collection</label>
            <select
              id={`${fieldId}-collection`}
              className={`${inputClass} w-48`}
              value={scope.collectionId ?? ""}
              onChange={(e) => onScopeChange({ collectionId: e.target.value || undefined })}
            >
              <option value="">All collections</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {scope.documentId ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
          <span>
            Entities in{" "}
            <Link
              href={`/library/${scope.documentId}`}
              className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
            >
              {documentTitle ?? "this document"}
            </Link>
          </span>
          <button
            type="button"
            className="text-brand-700 hover:underline"
            onClick={() => onScopeChange({})}
          >
            Show all documents
          </button>
        </p>
      ) : null}

      <Content
        scope={scope}
        loading={loading}
        error={error}
        graph={graph}
        types={types}
        hiddenTypes={hiddenTypes}
        onToggleType={toggleType}
        nodes={nodes}
        edges={edges}
        active={active}
        onActiveChange={setActive}
        onOpen={onOpen}
      />
    </div>
  );
}

type ContentProps = Pick<GraphViewProps, "scope" | "loading" | "error" | "graph" | "onOpen"> & {
  types: readonly string[];
  hiddenTypes: ReadonlySet<string>;
  onToggleType: (type: string) => void;
  nodes: Graph["nodes"];
  edges: Graph["edges"];
  active: string | null;
  onActiveChange: (id: string | null) => void;
};

function Content({
  scope,
  loading,
  error,
  graph,
  types,
  hiddenTypes,
  onToggleType,
  nodes,
  edges,
  active,
  onActiveChange,
  onOpen,
}: ContentProps) {
  if (error) {
    return <Alert>{error}</Alert>;
  }
  if (!graph) {
    return (
      <Card className="text-sm text-slate-500">
        <p aria-live="polite">{loading ? "Loading the graph…" : ""}</p>
      </Card>
    );
  }
  if (graph.nodes.length === 0) {
    return (
      <Card className="py-10 text-center">
        <p className="font-medium text-slate-900">No entities yet</p>
        <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
          {scope.documentId || scope.collectionId
            ? "No names or codes were found here. Try all documents."
            : "Names and codes are collected from documents after they are processed. Add a document or a note, or check back when processing has finished."}
        </p>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <Card className="space-y-3 p-3 sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
          <p aria-live="polite">
            {plural(nodes.length, "entity", "entities")} ·{" "}
            {plural(edges.length, "relation", "relations")}
            {graph.nodes.length === nodes.length ? "" : ` (of ${graph.nodes.length})`}
            {loading ? " · updating…" : ""}
          </p>
          <div role="group" aria-label="Entity types" className="flex flex-wrap gap-1">
            {types.map((type) => {
              const style = entityType(type);
              const shown = !hiddenTypes.has(type);
              return (
                <button
                  key={type}
                  type="button"
                  aria-pressed={shown}
                  onClick={() => onToggleType(type)}
                  className={cx(
                    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1",
                    shown
                      ? "border-slate-300 bg-white text-slate-700"
                      : "border-dashed border-slate-300 text-slate-400",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cx("size-2 rounded-full", shown ? style.dot : "bg-slate-300")}
                  />
                  {style.plural}
                </button>
              );
            })}
          </div>
        </div>
        {nodes.length > 0 ? (
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            active={active}
            onActiveChange={onActiveChange}
            onOpen={onOpen}
          />
        ) : (
          <p className="py-16 text-center text-sm text-slate-500">
            All entity types are hidden.
          </p>
        )}
        <p className="text-xs text-slate-500">
          Bigger circles are mentioned more often; thicker lines join entities that share more
          passages. Showing the most mentioned entities.
        </p>
      </Card>

      <Card className="p-0">
        <h2 className="border-b border-slate-200 px-4 py-3 text-sm font-medium">
          Most mentioned
        </h2>
        <ol aria-label="Entities" className="max-h-[32rem] divide-y divide-slate-100 overflow-y-auto">
          {nodes.map((node) => (
            <li
              key={node.id}
              onMouseEnter={() => onActiveChange(node.id)}
              onMouseLeave={() => onActiveChange(null)}
              className={cx("px-4 py-2", node.id === active && "bg-slate-50")}
            >
              <Link
                href={entityPath(node.id)}
                className="flex items-center gap-2 text-sm font-medium text-slate-900 hover:text-brand-700 hover:underline"
                onFocus={() => onActiveChange(node.id)}
                onBlur={() => onActiveChange(null)}
              >
                <span
                  aria-hidden="true"
                  className={cx("size-2 shrink-0 rounded-full", entityType(node.type).dot)}
                />
                <span className="truncate">{node.name}</span>
              </Link>
              <p className="pl-4 text-xs text-slate-500">
                {entityType(node.type).label} · {plural(node.mentions, "mention", "mentions")} ·{" "}
                {plural(node.documents, "document", "documents")}
              </p>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
