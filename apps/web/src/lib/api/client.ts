import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Problem = components["schemas"]["Problem"];
export type User = components["schemas"]["UserOut"];
export type DocumentItem = components["schemas"]["DocumentOut"];
export type DocumentPage = components["schemas"]["DocumentPage"];
export type DocumentStatus = DocumentItem["status"];
export type DocumentKind = DocumentItem["kind"];
export type Collection = components["schemas"]["CollectionOut"];
export type Note = components["schemas"]["NoteOut"];
export type Chunk = components["schemas"]["ChunkOut"];
export type ChunkPage = components["schemas"]["ChunkPage"];
export type SearchMode = components["schemas"]["SearchMode"];
export type SearchResult = components["schemas"]["SearchResultOut"];
export type SearchResponse = components["schemas"]["SearchResponse"];

/** Typed client for the KnowVault API. Requests go to the same origin and carry the session cookie. */
export const api = createClient<paths>({
  // Absolute same-origin URL: the Fetch API outside browsers rejects relative URLs.
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  credentials: "same-origin",
  // Resolve fetch at call time so tests (and instrumentation) can replace it.
  fetch: (request) => globalThis.fetch(request),
});

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | undefined;

  constructor(status: number, problem?: Problem) {
    super(problem?.detail ?? problem?.title ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).title === "string" &&
    typeof (value as Problem).code === "string"
  );
}

type ApiResult<T> = { data?: T; error?: unknown; response: Response };

/** Returns the response body, or throws an ApiError carrying the server's problem details. */
export async function unwrap<T>(request: Promise<ApiResult<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) {
    throw new ApiError(response.status, isProblem(error) ? error : undefined);
  }
  return data as T;
}

/** A message suitable for showing to the user. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422 && error.problem?.errors?.length) {
      return error.problem.errors.map((e) => String(e.msg)).join(" ");
    }
    return error.problem?.detail ?? error.problem?.title ?? error.message;
  }
  return "Something went wrong. Check your connection and try again.";
}
