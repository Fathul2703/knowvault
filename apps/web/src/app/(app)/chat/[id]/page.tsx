import type { Metadata } from "next";

import { ChatPage } from "@/features/chat/chat-page";

export const metadata: Metadata = { title: "Ask" };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChatPage key={id} conversationId={id} />;
}
