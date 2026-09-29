import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/login-form";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

function renderForm() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <LoginForm nextPath="/library" />
    </QueryClientProvider>,
  );
}

async function submit(email: string, password: string) {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

function jsonResponse(status: number, body: unknown, contentType = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

describe("LoginForm", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    replace.mockReset();
  });

  it("signs in and navigates to the requested page", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        id: "8b0f0b4e-3f5e-4a4a-9d3c-1b2c3d4e5f60",
        email: "ada@example.com",
        display_name: "Ada",
        created_at: "2026-09-01T10:00:00Z",
      }),
    );
    renderForm();
    await submit("ada@example.com", "correct horse battery");

    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/library"));
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(new URL(request.url).pathname).toBe("/api/v1/auth/login");
    expect(request.method).toBe("POST");
    expect(await request.json()).toEqual({
      email: "ada@example.com",
      password: "correct horse battery",
    });
  });

  it("shows the server's error and stays on the page", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        401,
        { type: "about:blank", title: "Invalid email or password", status: 401, code: "invalid_credentials" },
        "application/problem+json",
      ),
    );
    renderForm();
    await submit("ada@example.com", "wrong password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(replace).not.toHaveBeenCalled();
  });
});
