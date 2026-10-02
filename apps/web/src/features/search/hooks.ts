"use client";

import { useQuery } from "@tanstack/react-query";

import { api, ApiError, unwrap, type SearchMode, type SearchResponse } from "@/lib/api/client";

export const SEARCH_RESULT_LIMIT = 10;

export type SearchParams = { query: string; mode: SearchMode; collectionId?: string };

export function useSearch({ query, mode, collectionId }: SearchParams) {
  const text = query.trim();
  return useQuery<SearchResponse, ApiError>({
    queryKey: ["search", text, mode, collectionId ?? null],
    enabled: text.length > 0,
    // Results only change when documents do; avoid re-running the model on every focus.
    staleTime: 60_000,
    queryFn: () =>
      unwrap(
        api.POST("/api/v1/retrieval/search", {
          body: {
            query: text,
            mode,
            top_k: SEARCH_RESULT_LIMIT,
            collection_id: collectionId ?? null,
            document_ids: [],
          },
        }),
      ),
  });
}
