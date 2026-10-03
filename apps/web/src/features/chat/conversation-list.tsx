"use client";

import Link from "next/link";

import { buttonClass, cx } from "@/components/ui";
import { formatDate } from "@/features/library/format";
import { errorMessage } from "@/lib/api/client";

import { useConversations } from "./hooks";

export function ConversationList({ activeId }: { activeId?: string }) {
  const conversations = useConversations();
  const items = conversations.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <nav aria-label="Conversations" className="space-y-3">
      <Link href="/chat" className={buttonClass("secondary", "w-full")}>
        New conversation
      </Link>
      {conversations.isError ? (
        <p className="text-sm text-red-700">{errorMessage(conversations.error)}</p>
      ) : conversations.isPending ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-slate-500">No conversations yet.</p>
      ) : (
        <ul className="space-y-0.5">
          {items.map((conversation) => {
            const active = conversation.id === activeId;
            return (
              <li key={conversation.id}>
                <Link
                  href={`/chat/${conversation.id}`}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "block rounded-md px-2.5 py-2 text-sm",
                    active ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-100",
                  )}
                >
                  <span className="block truncate font-medium">
                    {conversation.title || "Untitled conversation"}
                  </span>
                  <span className="block text-xs text-slate-500">
                    {formatDate(conversation.updated_at)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {conversations.hasNextPage ? (
        <button
          type="button"
          className={buttonClass("ghost", "w-full")}
          disabled={conversations.isFetchingNextPage}
          onClick={() => conversations.fetchNextPage()}
        >
          Show more
        </button>
      ) : null}
    </nav>
  );
}
