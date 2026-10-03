"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";

import { Alert, Button, Card, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api/client";

import { useLogin } from "./hooks";

export function LoginForm({
  nextPath,
  accountDeleted = false,
}: {
  nextPath: string;
  accountDeleted?: boolean;
}) {
  const router = useRouter();
  const login = useLogin();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    login.mutate(
      { email: String(form.get("email")), password: String(form.get("password")) },
      { onSuccess: () => router.replace(nextPath) },
    );
  }

  return (
    <Card>
      <h1 className="mb-5 text-lg font-semibold">Sign in</h1>
      {accountDeleted ? (
        <p role="status" className="mb-4 rounded-md bg-slate-100 px-3 py-2 text-sm text-slate-700">
          Your account and all its data were deleted.
        </p>
      ) : null}
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Email" name="email" type="email" autoComplete="email" required />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
        />
        {login.isError ? <Alert>{errorMessage(login.error)}</Alert> : null}
        <Button type="submit" className="w-full" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-500">
        Have an invite code?{" "}
        <Link href="/register" className="font-medium text-brand-600 hover:underline">
          Create an account
        </Link>
      </p>
    </Card>
  );
}
