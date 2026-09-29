import type { Metadata } from "next";

import { NoteEditor } from "@/features/library/note-editor";

export const metadata: Metadata = { title: "New note" };

export default function NewNotePage() {
  return <NoteEditor />;
}
