import type { Metadata } from "next";

import { NoteEditor } from "@/features/library/note-editor";

export const metadata: Metadata = { title: "Edit note" };

export default async function EditNotePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <NoteEditor id={id} />;
}
