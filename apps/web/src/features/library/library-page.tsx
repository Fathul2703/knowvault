"use client";

import { useState } from "react";

import { errorMessage } from "@/lib/api/client";

import { CollectionsPanel } from "./collections-panel";
import { useCollections, useDocuments, useUploadDocument, type DocumentFilters } from "./hooks";
import { LibraryView } from "./library-view";

export function LibraryPage() {
  const [filters, setFilters] = useState<DocumentFilters>({});
  const documents = useDocuments(filters);
  const collections = useCollections();
  const upload = useUploadDocument();

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_16rem]">
      <LibraryView
        items={documents.data?.pages.flatMap((page) => page.items) ?? []}
        collections={collections.data ?? []}
        filters={filters}
        onFiltersChange={setFilters}
        onUpload={(file) => upload.mutate({ file, collectionId: filters.collectionId })}
        uploading={upload.isPending}
        uploadError={upload.isError ? errorMessage(upload.error) : null}
        loading={documents.isPending}
        loadError={documents.isError ? errorMessage(documents.error) : null}
        hasMore={documents.hasNextPage}
        loadingMore={documents.isFetchingNextPage}
        onLoadMore={() => documents.fetchNextPage()}
      />
      <aside className="xl:pt-[4.5rem]">
        <CollectionsPanel
          selectedId={filters.collectionId}
          onSelect={(collectionId) => setFilters({ ...filters, collectionId })}
        />
      </aside>
    </div>
  );
}
