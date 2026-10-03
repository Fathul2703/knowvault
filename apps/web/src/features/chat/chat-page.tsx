"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { Alert, Button, Card, inputClass } from "@/components/ui";
import { useCollections } from "@/features/library/hooks";
import { errorMessage, type Collection, type ConversationScope, type Message } from "@/lib/api/client";

import { Composer } from "./composer";
import { ConversationList } from "./conversation-list";
import { useAnswerStream, useConversation, useCreateConversation, useDeleteConversation } from "./hooks";
import { AssistantMessage, UserMessage, type AnswerView } from "./message";
import type { PendingTurn } from "./stream";

function scopeLabel(scope: ConversationScope, collections: readonly Collection[]): string {
  if (scope.collection_id) {
    const name = collections.find((c) => c.id === scope.collection_id)?.name;
    return name ? `Collection “${name}”` : "A collection";
  }
  if (scope.document_ids?.length) {
    return scope.document_ids.length === 1 ? "1 document" : `${scope.document_ids.length} documents`;
  }
  return "All documents";
}

function storedAnswer(message: Message): AnswerView {
  return {
    key: message.id,
    status: message.status,
    content: message.content,
    citations: message.citations,
    errorCode: message.error_code,
    live: false,
  };
}

function pendingAnswer(turn: PendingTurn): AnswerView {
  return {
    key: turn.messageId ?? "pending",
    status: turn.status,
    content: turn.content,
    citations: turn.citations,
    errorCode: turn.errorCode,
    live: true,
  };
}

/**
 * Conversations with streamed, cited answers. `/chat` starts a new conversation; it is created
 * with the first question, and the address changes to `/chat/<id>` without reloading, so the
 * answer keeps streaming.
 */
export function ChatPage({ conversationId }: { conversationId?: string }) {
  const pathname = usePathname();
  // Returning to /chat from a conversation started here begins a fresh one. The page itself is
  // not re-mounted by that navigation, so the session is.
  const [session, setSession] = useState(0);
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    setLastPath(pathname);
    if (!conversationId && pathname === "/chat") {
      setSession((n) => n + 1);
    }
  }
  return <ChatSession key={session} routeId={conversationId} />;
}

function ChatSession({ routeId }: { routeId?: string }) {
  const router = useRouter();
  const fieldId = useId();
  const [createdId, setCreatedId] = useState<string>();
  const conversationId = routeId ?? createdId;

  const collections = useCollections();
  const detail = useConversation(conversationId);
  const create = useCreateConversation();
  const remove = useDeleteConversation();
  const stream = useAnswerStream();

  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [collectionId, setCollectionId] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const turn = stream.turn;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [turn?.question, turn?.status, detail.data?.messages.length]);

  async function ask(question: string) {
    setError(null);
    let target = conversationId;
    if (!target) {
      try {
        const conversation = await create.mutateAsync({
          collection_id: collectionId || null,
          document_ids: [],
        });
        target = conversation.id;
        setCreatedId(target);
        window.history.replaceState(null, "", `/chat/${target}`);
      } catch (cause) {
        setError(errorMessage(cause));
        return;
      }
    }
    setDraft("");
    const result = await stream.ask(target, question);
    if (!result.ok) {
      setError(result.error);
      setDraft(question);
    }
  }

  const stored = detail.data?.messages ?? [];
  // The live turn is shown until the stored conversation has its finished answer.
  const pendingDone =
    turn?.messageId != null &&
    stored.some((m) => m.id === turn.messageId && m.status !== "streaming");
  const showPending = turn != null && !pendingDone;
  // Meanwhile the stored copy of the same turn (the question and an answer still streaming) is
  // hidden, even if it was loaded before the stream said which messages it created. Only one
  // answer per user streams at a time, so a trailing streaming answer is this one.
  let messages = stored;
  if (showPending && messages.at(-1)?.role === "assistant" && messages.at(-1)?.status === "streaming") {
    messages = messages.slice(0, -1);
    if (messages.at(-1)?.role === "user") {
      messages = messages.slice(0, -1);
    }
  }

  const notFound = detail.error?.status === 404;
  const title = detail.data?.title || (conversationId ? "Untitled conversation" : "New conversation");
  const empty = messages.length === 0 && !showPending;

  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="hidden lg:block">
        <ConversationList activeId={conversationId} />
      </aside>

      <div className="flex min-h-[70vh] min-w-0 flex-col">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {detail.data
                ? `Answers use: ${scopeLabel(detail.data.scope, collections.data ?? [])}`
                : "Answers come only from your documents and cite the passages they use."}
            </p>
          </div>
          {conversationId && detail.data ? (
            <Button
              variant="danger"
              disabled={remove.isPending || stream.streaming}
              onClick={() => {
                if (window.confirm(`Delete “${title}”? This cannot be undone.`)) {
                  remove.mutate(conversationId, { onSuccess: () => router.push("/chat") });
                }
              }}
            >
              Delete
            </Button>
          ) : null}
        </header>

        <details className="mt-3 lg:hidden">
          <summary className="cursor-pointer text-sm font-medium text-slate-600">Conversations</summary>
          <div className="mt-2">
            <ConversationList activeId={conversationId} />
          </div>
        </details>

        <section aria-label="Messages" className="flex-1 space-y-5 py-6">
          {notFound ? (
            <Alert>This conversation does not exist or was deleted.</Alert>
          ) : detail.isError ? (
            <Alert>{errorMessage(detail.error)}</Alert>
          ) : conversationId && detail.isPending && !showPending ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : empty ? (
            <Card className="space-y-2 text-sm text-slate-600">
              <p className="font-medium text-slate-900">Ask a question about your documents</p>
              <ul className="list-disc space-y-1 pl-5">
                <li>Answers use only your ready documents and cite them as [1], [2]…; select a number to see the passage.</li>
                <li>If your documents do not contain the answer, KnowVault says so instead of guessing.</li>
                <li>Follow-up questions can refer to earlier answers in the conversation.</li>
              </ul>
            </Card>
          ) : null}

          {messages.map((message) => {
            if (message.role === "user") {
              return <UserMessage key={message.id} content={message.content} />;
            }
            return <AssistantMessage key={message.id} answer={storedAnswer(message)} />;
          })}
          {showPending && turn ? (
            <>
              <UserMessage content={turn.question} />
              <AssistantMessage answer={pendingAnswer(turn)} />
            </>
          ) : null}
          <div ref={end} />
        </section>

        {notFound ? null : (
          <div className="sticky bottom-0 space-y-3 border-t border-slate-200 bg-slate-50 pb-2 pt-4">
            {error ? <Alert>{error}</Alert> : null}
            {!conversationId ? (
              <div className="flex items-center gap-2 text-sm text-slate-600">
                <label htmlFor={`${fieldId}-scope`} className="whitespace-nowrap">
                  Search in
                </label>
                <select
                  id={`${fieldId}-scope`}
                  className={`${inputClass} w-56`}
                  value={collectionId}
                  onChange={(e) => setCollectionId(e.target.value)}
                >
                  <option value="">All documents</option>
                  {(collections.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <Composer
              value={draft}
              onChange={setDraft}
              onSubmit={ask}
              busy={stream.streaming || create.isPending}
            />
          </div>
        )}
      </div>
    </div>
  );
}
