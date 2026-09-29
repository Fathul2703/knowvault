import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-2xl font-semibold tracking-tight text-slate-900">KnowVault</p>
          <p className="mt-1 text-sm text-slate-500">Your knowledge, answerable and cited.</p>
        </div>
        {children}
      </div>
    </main>
  );
}
