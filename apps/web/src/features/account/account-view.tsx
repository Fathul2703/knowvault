"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { Alert, Button, Card, inputClass } from "@/components/ui";
import { useCurrentUser } from "@/features/auth/hooks";
import { formatDate } from "@/features/library/format";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api/client";

export function useDeleteAccount() {
  return useMutation<void, ApiError, string>({
    mutationFn: async (password) => {
      await unwrap(api.DELETE("/api/v1/auth/me", { body: { password } }));
    },
  });
}

export function AccountView() {
  const { data: user } = useCurrentUser();
  const remove = useDeleteAccount();
  const router = useRouter();
  const queryClient = useQueryClient();
  const fieldId = useId();
  const [password, setPassword] = useState("");
  if (!user) {
    return null;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !window.confirm(
        "Delete your account and everything in it? Documents, notes, collections and " +
          "conversations are removed permanently.",
      )
    ) {
      return;
    }
    remove.mutate(password, {
      onSuccess: () => {
        // Nothing cached from the deleted account may survive.
        queryClient.clear();
        router.replace("/login?deleted=1");
      },
    });
  }

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Account</h1>

      <Card className="space-y-1 text-sm">
        <p className="font-medium text-slate-900">{user.display_name}</p>
        <p className="text-slate-600">{user.email}</p>
        <p className="text-slate-500">Member since {formatDate(user.created_at)}</p>
      </Card>

      <Card className="space-y-4 border-red-200">
        <div>
          <h2 className="font-medium text-red-800">Delete account</h2>
          <p className="mt-1 text-sm text-slate-600">
            Permanently deletes your account with all documents and their files, notes,
            collections and conversations. This cannot be undone.
          </p>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label htmlFor={fieldId} className="block text-sm font-medium text-slate-700">
              Current password
            </label>
            <input
              id={fieldId}
              type="password"
              autoComplete="current-password"
              required
              className={`${inputClass} mt-1`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {remove.isError ? <Alert>{errorMessage(remove.error)}</Alert> : null}
          <Button type="submit" variant="danger" disabled={!password || remove.isPending}>
            {remove.isPending ? "Deleting…" : "Delete my account"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
