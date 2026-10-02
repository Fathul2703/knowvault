import type { Metadata } from "next";

import { SearchPage } from "@/features/search/search-page";
import type { SearchMode } from "@/lib/api/client";

export const metadata: Metadata = { title: "Search" };

const MODES: readonly SearchMode[] = ["hybrid", "vector", "fulltext"];

type Params = { q?: string | string[]; mode?: string | string[]; collection?: string | string[] };

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Page({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const mode = first(params.mode);
  return (
    <SearchPage
      query={(first(params.q) ?? "").trim()}
      mode={MODES.includes(mode as SearchMode) ? (mode as SearchMode) : "hybrid"}
      collectionId={first(params.collection) || undefined}
    />
  );
}
