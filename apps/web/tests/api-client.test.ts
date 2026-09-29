import { describe, expect, it } from "vitest";

import { ApiError, errorMessage, unwrap, type Problem } from "@/lib/api/client";

function result<T>(status: number, body: { data?: T; error?: unknown }) {
  return Promise.resolve({ ...body, response: new Response(null, { status }) });
}

describe("unwrap", () => {
  it("returns data for successful responses", async () => {
    await expect(unwrap(result(200, { data: { id: "1" } }))).resolves.toEqual({ id: "1" });
  });

  it("throws ApiError with the problem details", async () => {
    const problem: Problem = {
      type: "about:blank",
      title: "Invalid email or password",
      status: 401,
      code: "invalid_credentials",
    };
    const error = await unwrap(result(401, { error: problem })).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).problem?.code).toBe("invalid_credentials");
  });

  it("tolerates non-problem error bodies", async () => {
    const error = await unwrap(result(502, { error: "Bad gateway" })).catch((e: unknown) => e);
    expect((error as ApiError).problem).toBeUndefined();
  });
});

describe("errorMessage", () => {
  it("prefers the problem detail", () => {
    const error = new ApiError(429, {
      type: "about:blank",
      title: "Too many requests",
      status: 429,
      code: "rate_limited",
      detail: "Too many failed login attempts. Try again later.",
    });
    expect(errorMessage(error)).toBe("Too many failed login attempts. Try again later.");
  });

  it("lists validation messages", () => {
    const error = new ApiError(422, {
      type: "about:blank",
      title: "Validation failed",
      status: 422,
      code: "validation_error",
      errors: [{ loc: ["body", "password"], msg: "String should have at least 12 characters" }],
    });
    expect(errorMessage(error)).toBe("String should have at least 12 characters");
  });

  it("falls back to a generic message for network errors", () => {
    expect(errorMessage(new TypeError("Failed to fetch"))).toMatch(/Something went wrong/);
  });
});
