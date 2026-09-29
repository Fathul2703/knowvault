"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { Alert, Button, Card, inputClass } from "@/components/ui";
import { errorMessage, type Note } from "@/lib/api/client";

import { useCollections, useNote, useSaveNote } from "./hooks";

export const NOTE_MAX_CHARS = 200_000;

/** Creates a note, or edits one when `id` is given. */
export function NoteEditor({ id }: { id?: string }) {
  const note = useNote(id);
  if (id && note.isError) {
    return <Alert>{errorMessage(note.error)}</Alert>;
  }
  if (id && !note.data) {
    return <p className="text-sm text-slate-500">Loading…</p>;
  }
  return <NoteForm id={id} initial={id ? note.data : undefined} />;
}

function NoteForm({ id, initial }: { id?: string; initial?: Note }) {
  const router = useRouter();
  const save = useSaveNote(id);
  const collections = useCollections();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body_md ?? "");
  const [collectionId, setCollectionId] = useState("");
  const fieldId = useId();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(
      { title: title.trim(), body_md: body, collection_id: collectionId || null },
      { onSuccess: (saved) => router.push(`/library/${saved.id}`) },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link
            href={id ? `/library/${id}` : "/library"}
            className="text-sm text-brand-600 hover:underline"
          >
            ← {id ? "Back to note" : "Library"}
          </Link>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {id ? "Edit note" : "New note"}
          </h1>
        </div>
        <Button type="submit" disabled={save.isPending || !title.trim() || !body.trim()}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
      </div>

      {save.isError ? <Alert>{errorMessage(save.error)}</Alert> : null}

      <Card className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor={`${fieldId}-title`} className="block text-sm font-medium text-slate-700">
            Title
          </label>
          <input
            id={`${fieldId}-title`}
            className={inputClass}
            value={title}
            maxLength={300}
            required
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        {!id ? (
          <div className="space-y-1.5">
            <label
              htmlFor={`${fieldId}-collection`}
              className="block text-sm font-medium text-slate-700"
            >
              Collection
            </label>
            <select
              id={`${fieldId}-collection`}
              className={inputClass}
              value={collectionId}
              onChange={(e) => setCollectionId(e.target.value)}
            >
              <option value="">No collection</option>
              {collections.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="space-y-1.5">
          <label htmlFor={`${fieldId}-body`} className="block text-sm font-medium text-slate-700">
            Content (Markdown)
          </label>
          <textarea
            id={`${fieldId}-body`}
            className={`${inputClass} min-h-[24rem] font-mono`}
            value={body}
            maxLength={NOTE_MAX_CHARS}
            required
            onChange={(e) => setBody(e.target.value)}
          />
        </div>
        <p className="text-xs text-slate-500">
          Use <code># Headings</code> to structure longer notes; they are kept as context for each
          passage. Saving re-processes the note.
        </p>
      </Card>
    </form>
  );
}
