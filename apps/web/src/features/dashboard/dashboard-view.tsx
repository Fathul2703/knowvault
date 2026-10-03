"use client";

import Link from "next/link";

import { Badge, Card } from "@/components/ui";
import { useCurrentUser } from "@/features/auth/hooks";

const ROADMAP = [
  { title: "Sign in securely", detail: "Invite-based accounts with server-side sessions.", phase: "Phase 1", done: true },
  { title: "Build your library", detail: "Upload PDFs, Word files and Markdown, or write notes.", phase: "Phase 2", done: true },
  { title: "Search by meaning", detail: "Hybrid semantic and keyword search across everything.", phase: "Phase 3", done: true },
  { title: "Ask with citations", detail: "Answers grounded in your documents, with sources.", phase: "Phase 4", done: true },
] as const;

const memberSince = new Intl.DateTimeFormat("en", { dateStyle: "long" });

export function DashboardView() {
  const { data: user } = useCurrentUser();
  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {user.display_name}</h1>
        <p className="mt-1 text-sm text-slate-500">
          Member since {memberSince.format(new Date(user.created_at))}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="font-medium">Getting started</h2>
          <ol className="mt-4 space-y-4">
            {ROADMAP.map((step) => (
              <li key={step.title} className="flex items-start justify-between gap-4">
                <div>
                  <p className={step.done ? "text-slate-900" : "text-slate-700"}>{step.title}</p>
                  <p className="text-sm text-slate-500">{step.detail}</p>
                </div>
                <Badge tone={step.done ? "success" : "neutral"}>
                  {step.done ? "Done" : step.phase}
                </Badge>
              </li>
            ))}
          </ol>
        </Card>

        <div className="space-y-6">
          <Card>
            <h2 className="font-medium">Library</h2>
            <p className="mt-2 text-sm text-slate-500">
              Your documents and notes live in the library.
            </p>
            <Link
              href="/library"
              className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline"
            >
              Open library →
            </Link>
          </Card>

          <Card>
            <h2 className="font-medium">Ask</h2>
            <p className="mt-2 text-sm text-slate-500">
              Ask questions and get answers that cite your documents.
            </p>
            <Link
              href="/chat"
              className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline"
            >
              Start a conversation →
            </Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
