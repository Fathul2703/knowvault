"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useCollections } from "@/features/library/hooks";
import { errorMessage, type SearchMode } from "@/lib/api/client";

import { useSearch, type SearchParams } from "./hooks";
import { SearchView } from "./search-view";

/** Shows "this may take a while" after this long. */
const SLOW_AFTER_MS = 3000;

export function searchUrl({ query, mode, collectionId }: SearchParams): string {
  const params = new URLSearchParams({ q: query });
  if (mode !== "hybrid") {
    params.set("mode", mode);
  }
  if (collectionId) {
    params.set("collection", collectionId);
  }
  return `/search?${params.toString()}`;
}

/**
 * The URL is the source of truth for the search, so results can be shared and the browser's
 * back and forward buttons move between searches.
 */
export function SearchPage({
  query,
  mode,
  collectionId,
}: {
  query: string;
  mode: SearchMode;
  collectionId?: string;
}) {
  const router = useRouter();
  const collections = useCollections();
  const search = useSearch({ query, mode, collectionId });
  const loading = search.isFetching && !search.data;

  // Remembers which search has been running for a while; any other search starts "not slow".
  const searchKey = `${query}|${mode}|${collectionId ?? ""}`;
  const [slowKey, setSlowKey] = useState<string | null>(null);
  useEffect(() => {
    if (!loading) {
      return;
    }
    const timer = setTimeout(() => setSlowKey(searchKey), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, [loading, searchKey]);
  const slow = loading && slowKey === searchKey;

  return (
    <SearchView
      // Re-mount on navigation so the input shows the query of the current URL.
      key={searchKey}
      query={query}
      mode={mode}
      collectionId={collectionId}
      collections={collections.data ?? []}
      onSearch={(params) => router.push(searchUrl(params))}
      loading={loading}
      slow={slow}
      error={search.isError ? errorMessage(search.error) : null}
      response={search.data}
    />
  );
}
