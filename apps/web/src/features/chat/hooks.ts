"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  api,
  ApiError,
  errorMessage,
  unwrap,
  type Conversation,
  type ConversationDetail,
  type ConversationPage,
  type ConversationScope,
} from "@/lib/api/client";

import { applyEvent, startTurn, streamAnswer, type PendingTurn } from "./stream";

export const chatKeys = {
  all: ["chat"] as const,
  conversations: ["chat", "conversations"] as const,
  conversation: (id: string) => ["chat", "conversation", id] as const,
};

export function useConversations() {
  return useInfiniteQuery<ConversationPage, ApiError>({
    queryKey: chatKeys.conversations,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/conversations", {
          params: { query: { cursor: pageParam as string | undefined, limit: 50 } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useConversation(id: string | undefined) {
  return useQuery<ConversationDetail, ApiError>({
    queryKey: chatKeys.conversation(id ?? ""),
    enabled: Boolean(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/conversations/{conversation_id}", {
          params: { path: { conversation_id: id ?? "" } },
        }),
      ),
  });
}

export function useCreateConversation() {
  return useMutation<Conversation, ApiError, ConversationScope>({
    mutationFn: (scope) =>
      unwrap(api.POST("/api/v1/conversations", { body: { title: "", scope } })),
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: async (id) => {
      await unwrap(
        api.DELETE("/api/v1/conversations/{conversation_id}", {
          params: { path: { conversation_id: id } },
        }),
      );
    },
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: chatKeys.conversation(id) });
      return queryClient.invalidateQueries({ queryKey: chatKeys.conversations });
    },
  });
}

export type AskResult = { ok: true } | { ok: false; error: string };

/**
 * Streams answers into a pending turn. Leaving the page stops the answer: the request is
 * aborted and the API stores it as interrupted.
 */
export function useAnswerStream() {
  const queryClient = useQueryClient();
  const [turn, setTurn] = useState<PendingTurn | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const ask = useCallback(
    async (conversationId: string, question: string): Promise<AskResult> => {
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      setTurn(startTurn(question));
      try {
        await streamAnswer(conversationId, question, {
          signal: abort.signal,
          onEvent: (event) => setTurn((current) => current && applyEvent(current, event)),
        });
        return { ok: true };
      } catch (error) {
        if (abort.signal.aborted) {
          return { ok: true };
        }
        if (error instanceof ApiError) {
          // Nothing was stored: the question goes back to the composer.
          setTurn(null);
          return { ok: false, error: errorMessage(error) };
        }
        setTurn((current) =>
          current && current.status === "streaming"
            ? {
                ...current,
                status: "error",
                errorCode: "connection_lost",
                errorDetail: "The connection was lost while the answer was being written.",
              }
            : current,
        );
        return { ok: true };
      } finally {
        if (controller.current === abort) {
          controller.current = null;
        }
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: chatKeys.conversation(conversationId) }),
          queryClient.invalidateQueries({ queryKey: chatKeys.conversations }),
        ]);
      }
    },
    [queryClient],
  );

  return { turn, ask, streaming: turn?.status === "streaming" };
}
