"use client";

import { useState, type FormEvent } from "react";

import { Alert, Button, Card, inputClass } from "@/components/ui";
import { errorMessage } from "@/lib/api/client";

import {
  useCollections,
  useCreateCollection,
  useDeleteCollection,
  useRenameCollection,
} from "./hooks";

export function CollectionsPanel({
  selectedId,
  onSelect,
}: {
  selectedId?: string;
  onSelect: (id: string | undefined) => void;
}) {
  const collections = useCollections();
  const create = useCreateCollection();
  const rename = useRenameCollection();
  const remove = useDeleteCollection();
  const [name, setName] = useState("");
  const error = create.error ?? rename.error ?? remove.error;

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    create.mutate({ name: name.trim() }, { onSuccess: () => setName("") });
  }

  return (
    <Card className="space-y-4">
      <h2 className="font-medium">Collections</h2>
      <ul className="space-y-1 text-sm">
        {collections.data?.map((collection) => (
          <li key={collection.id} className="group flex items-center justify-between gap-2">
            <button
              type="button"
              aria-pressed={selectedId === collection.id}
              onClick={() => onSelect(selectedId === collection.id ? undefined : collection.id)}
              className={`min-w-0 flex-1 truncate rounded px-2 py-1 text-left ${
                selectedId === collection.id
                  ? "bg-brand-50 font-medium text-brand-700"
                  : "text-slate-700 hover:bg-slate-100"
              }`}
            >
              {collection.name}{" "}
              <span className="text-xs text-slate-400">{collection.document_count}</span>
            </button>
            <span className="flex shrink-0 gap-1 text-xs opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
              <button
                type="button"
                className="text-slate-500 hover:text-slate-900"
                onClick={() => {
                  const next = window.prompt("Rename collection", collection.name);
                  if (next && next.trim() && next.trim() !== collection.name) {
                    rename.mutate({ id: collection.id, name: next.trim() });
                  }
                }}
              >
                Rename
              </button>
              <button
                type="button"
                className="text-red-600 hover:text-red-800"
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete “${collection.name}”? Its documents stay in your library.`,
                    )
                  ) {
                    if (selectedId === collection.id) {
                      onSelect(undefined);
                    }
                    remove.mutate(collection.id);
                  }
                }}
              >
                Delete
              </button>
            </span>
          </li>
        ))}
        {collections.data?.length === 0 ? (
          <li className="px-2 text-slate-500">No collections yet.</li>
        ) : null}
      </ul>
      <form onSubmit={handleCreate} className="flex gap-2">
        <input
          className={inputClass}
          placeholder="New collection"
          aria-label="New collection name"
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Button type="submit" variant="secondary" disabled={create.isPending || !name.trim()}>
          Add
        </Button>
      </form>
      {error ? <Alert>{errorMessage(error)}</Alert> : null}
    </Card>
  );
}
