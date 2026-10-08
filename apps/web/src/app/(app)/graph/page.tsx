import type { Metadata } from "next";

import { GraphPage } from "@/features/graph/graph-page";

export const metadata: Metadata = { title: "Graph" };

type Params = { collection?: string | string[]; document?: string | string[] };

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Page({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const documentId = first(params.document) || undefined;
  return (
    <GraphPage
      // A document already belongs to one collection; the document wins.
      collectionId={documentId ? undefined : first(params.collection) || undefined}
      documentId={documentId}
    />
  );
}
