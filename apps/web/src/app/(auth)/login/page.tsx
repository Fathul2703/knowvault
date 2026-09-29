import type { Metadata } from "next";

import { LoginForm } from "@/features/auth/login-form";
import { safeNextPath } from "@/lib/navigation";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  return <LoginForm nextPath={safeNextPath(typeof next === "string" ? next : undefined)} />;
}
