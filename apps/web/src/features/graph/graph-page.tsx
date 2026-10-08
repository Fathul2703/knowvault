"use client";

import { useRouter } from "next/navigation";

import { useCollections, useDocument } from "@/features/library/hooks";
import { errorMessage } from "@/lib/api/client";

import { entityPath } from "./entity-types";
import { GraphView } from "./graph-view";
import { useGraph, type GraphScope } from "./hooks";

export function graphUrl({ collectionId, documentId }: GraphScope): string {
  const params = new URLSearchParams();
  if (documentId) {
    params.set("document", documentId);
  } else if (collectionId) {
    params.set("collection", collectionId);
  }
  const query = params.toString();
  return query ? `/graph?${query}` : "/graph";
}

/** The URL holds the scope, so a filtered graph can be linked to and revisited. */
export function GraphPage(scope: GraphScope) {
  const router = useRouter();
  const collections = useCollections();
  const graph = useGraph(scope);
  const document = useDocument(scope.documentId ?? "", { enabled: Boolean(scope.documentId) });

  return (
    <GraphView
      scope={scope}
      documentTitle={document.data?.title}
      collections={collections.data ?? []}
      onScopeChange={(next) => router.push(graphUrl(next))}
      onOpen={(id) => router.push(entityPath(id))}
      loading={graph.isFetching}
      error={graph.isError ? errorMessage(graph.error) : null}
      // A different scope keeps showing the previous graph until it loads; never mix them up
      // when the request failed.
      graph={graph.isError ? undefined : graph.data}
    />
  );
}
