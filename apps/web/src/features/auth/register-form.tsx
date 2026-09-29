"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";

import { Alert, Button, Card, Field } from "@/components/ui";
import { errorMessage } from "@/lib/api/client";
import { DEFAULT_AUTHENTICATED_PATH } from "@/lib/navigation";

import { useRegister } from "./hooks";

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

export function RegisterForm() {
  const router = useRouter();
  const register = useRegister();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    register.mutate(
      {
        invite_code: String(form.get("invite_code")).trim(),
        email: String(form.get("email")),
        display_name: String(form.get("display_name")).trim(),
        password: String(form.get("password")),
      },
      { onSuccess: () => router.replace(DEFAULT_AUTHENTICATED_PATH) },
    );
  }

  return (
    <Card>
      <h1 className="mb-1 text-lg font-semibold">Create your account</h1>
      <p className="mb-5 text-sm text-slate-500">KnowVault is invite-only for now.</p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <Field label="Invite code" name="invite_code" autoComplete="off" required />
        <Field label="Name" name="display_name" autoComplete="name" maxLength={100} required />
        <Field label="Email" name="email" type="email" autoComplete="email" required />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          minLength={PASSWORD_MIN_LENGTH}
          maxLength={PASSWORD_MAX_LENGTH}
          hint={`At least ${PASSWORD_MIN_LENGTH} characters.`}
          required
        />
        {register.isError ? <Alert>{errorMessage(register.error)}</Alert> : null}
        <Button type="submit" className="w-full" disabled={register.isPending}>
          {register.isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-600 hover:underline">
          Sign in
        </Link>
      </p>
    </Card>
  );
}
