import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AccountView } from "@/features/account/account-view";
import { currentUserKey } from "@/features/auth/hooks";

const fetchMock = vi.fn<typeof fetch>();
const assign = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: assign, push: vi.fn() }) }));

function renderAccount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(currentUserKey, {
    id: "u1",
    email: "ada@example.com",
    display_name: "Ada",
    created_at: "2026-09-01T10:00:00Z",
  });
  render(
    <QueryClientProvider client={client}>
      <AccountView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  fetchMock.mockReset();
  assign.mockReset();
});

describe("AccountView", () => {
  it("deletes the account with the password after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    renderAccount();

    await userEvent.type(screen.getByLabelText("Current password"), "secret password");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));

    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("/login?deleted=1"));
    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("DELETE");
    expect(new URL(request.url).pathname).toBe("/api/v1/auth/me");
    expect(await request.json()).toEqual({ password: "secret password" });
  });

  it("shows a wrong password and keeps the account", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          type: "about:blank",
          title: "The password is not correct",
          status: 403,
          code: "invalid_password",
        }),
        { status: 403, headers: { "Content-Type": "application/problem+json" } },
      ),
    );
    renderAccount();

    await userEvent.type(screen.getByLabelText("Current password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The password is not correct");
    expect(assign).not.toHaveBeenCalled();
  });

  it("does nothing when the confirmation is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderAccount();
    await userEvent.type(screen.getByLabelText("Current password"), "secret password");
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
