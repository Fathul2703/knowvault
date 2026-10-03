import type { Metadata } from "next";

import { ChatPage } from "@/features/chat/chat-page";

export const metadata: Metadata = { title: "Ask" };

export default function Page() {
  return <ChatPage />;
}
