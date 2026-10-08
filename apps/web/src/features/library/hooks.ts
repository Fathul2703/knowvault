"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  api,
  ApiError,
  unwrap,
  type ChunkPage,
  type Collection,
  type DocumentItem,
  type DocumentKind,
  type DocumentPage,
  type Note,
} from "@/lib/api/client";

/** How often to refresh while a document is still being processed. */
export const PROCESSING_POLL_MS = 1500;

export const libraryKeys = {
  all: ["library"] as const,
  documents: (filters: DocumentFilters) => ["library", "documents", filters] as const,
  document: (id: string) => ["library", "document", id] as const,
  chunks: (id: string) => ["library", "chunks", id] as const,
  note: (id: string) => ["library", "note", id] as const,
  collections: ["library", "collections"] as const,
};

export type DocumentFilters = { kind?: DocumentKind; collectionId?: string };

export function isProcessing(document: Pick<DocumentItem, "status">): boolean {
  return document.status === "pending" || document.status === "processing";
}

function invalidateLibrary(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: libraryKeys.all });
}

// --- Documents -----------------------------------------------------------------------------

export function useDocuments(filters: DocumentFilters) {
  return useInfiniteQuery<DocumentPage, ApiError>({
    queryKey: libraryKeys.documents(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/documents", {
          params: {
            query: {
              kind: filters.kind,
              collection_id: filters.collectionId,
              cursor: pageParam as string | undefined,
              limit: 50,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: (query) =>
      query.state.data?.pages.some((page) => page.items.some(isProcessing))
        ? PROCESSING_POLL_MS
        : false,
  });
}

export function useDocument(id: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery<DocumentItem, ApiError>({
    queryKey: libraryKeys.document(id),
    enabled,
    queryFn: () =>
      unwrap(api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } })),
    refetchInterval: (query) =>
      query.state.data && isProcessing(query.state.data) ? PROCESSING_POLL_MS : false,
  });
}

export function useChunks(id: string, enabled: boolean) {
  return useInfiniteQuery<ChunkPage, ApiError>({
    queryKey: libraryKeys.chunks(id),
    enabled,
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/documents/{document_id}/chunks", {
          params: { path: { document_id: id }, query: { offset: pageParam as number, limit: 50 } },
        }),
      ),
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((sum, page) => sum + page.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });
}

export async function uploadDocument(file: File, collectionId?: string): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  if (collectionId) {
    form.append("collection_id", collectionId);
  }
  return unwrap(
    api.POST("/api/v1/documents", {
      // The generated type describes the multipart fields; the browser sends the FormData as is.
      body: form as unknown as { file: string },
      bodySerializer: (body) => body as unknown as FormData,
    }),
  );
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation<DocumentItem, ApiError, { file: File; collectionId?: string }>({
    mutationFn: ({ file, collectionId }) => uploadDocument(file, collectionId),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}

export function useUpdateDocument(id: string) {
  const queryClient = useQueryClient();
  return useMutation<
    DocumentItem,
    ApiError,
    { title?: string; collection_id?: string | null }
  >({
    mutationFn: (body) =>
      unwrap(
        api.PATCH("/api/v1/documents/{document_id}", {
          params: { path: { document_id: id } },
          body,
        }),
      ),
    onSuccess: (document) => {
      queryClient.setQueryData(libraryKeys.document(id), document);
      return invalidateLibrary(queryClient);
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.DELETE("/api/v1/documents/{document_id}", { params: { path: { document_id: id } } }),
      ),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}

export function useReprocessDocument(id: string) {
  const queryClient = useQueryClient();
  return useMutation<DocumentItem, ApiError>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/documents/{document_id}/reprocess", {
          params: { path: { document_id: id } },
        }),
      ),
    onSuccess: (document) => {
      queryClient.setQueryData(libraryKeys.document(id), document);
      return invalidateLibrary(queryClient);
    },
  });
}

// --- Notes ---------------------------------------------------------------------------------

export function useNote(id: string | undefined) {
  return useQuery<Note, ApiError>({
    queryKey: libraryKeys.note(id ?? ""),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/notes/{document_id}", { params: { path: { document_id: id ?? "" } } }),
      ),
  });
}

export type NoteInput = { title: string; body_md: string; collection_id?: string | null };

export function useSaveNote(id?: string) {
  const queryClient = useQueryClient();
  return useMutation<Note, ApiError, NoteInput>({
    mutationFn: (body) =>
      id
        ? unwrap(
            api.PUT("/api/v1/notes/{document_id}", {
              params: { path: { document_id: id } },
              body: { title: body.title, body_md: body.body_md },
            }),
          )
        : unwrap(api.POST("/api/v1/notes", { body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}

// --- Collections ---------------------------------------------------------------------------

export function useCollections() {
  return useQuery<Collection[], ApiError>({
    queryKey: libraryKeys.collections,
    queryFn: () => unwrap(api.GET("/api/v1/collections")),
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();
  return useMutation<Collection, ApiError, { name: string }>({
    mutationFn: (body) => unwrap(api.POST("/api/v1/collections", { body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}

export function useRenameCollection() {
  const queryClient = useQueryClient();
  return useMutation<Collection, ApiError, { id: string; name: string }>({
    mutationFn: ({ id, name }) =>
      unwrap(
        api.PATCH("/api/v1/collections/{collection_id}", {
          params: { path: { collection_id: id } },
          body: { name },
        }),
      ),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.DELETE("/api/v1/collections/{collection_id}", {
          params: { path: { collection_id: id } },
        }),
      ),
    onSuccess: () => invalidateLibrary(queryClient),
  });
}
