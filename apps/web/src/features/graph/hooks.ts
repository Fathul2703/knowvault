"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, ApiError, unwrap, type Entity, type Graph } from "@/lib/api/client";

/** Entities drawn in the overview; the API allows up to 200. */
export const GRAPH_NODE_LIMIT = 60;

export type GraphScope = { collectionId?: string; documentId?: string };

export const graphKeys = {
  all: ["graph"] as const,
  overview: (scope: GraphScope) =>
    ["graph", "overview", scope.collectionId ?? null, scope.documentId ?? null] as const,
  entity: (id: string) => ["graph", "entity", id] as const,
};

export function useGraph(scope: GraphScope) {
  return useQuery<Graph, ApiError>({
    queryKey: graphKeys.overview(scope),
    // Keep the old picture on screen while another scope loads.
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/graph", {
          params: {
            query: {
              collection_id: scope.collectionId,
              document_id: scope.documentId,
              limit: GRAPH_NODE_LIMIT,
            },
          },
        }),
      ),
  });
}

export function useEntity(id: string) {
  return useQuery<Entity, ApiError>({
    queryKey: graphKeys.entity(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/graph/entities/{entity_id}", {
          params: { path: { entity_id: id } },
        }),
      ),
  });
}
