"use client";

import Link from "next/link";

import { Alert, Badge, Card, buttonClass, cx } from "@/components/ui";
import { highlightSegments } from "@/features/search/highlight";
import { searchUrl } from "@/features/search/search-page";
import { errorMessage, type Entity, type EntityMention } from "@/lib/api/client";

import { entityPath, entityType, plural } from "./entity-types";
import { useEntity } from "./hooks";

/** The API returns at most this many passages per entity. */
export const MENTION_LIMIT = 50;

export function EntityPage({ id }: { id: string }) {
  const entity = useEntity(id);
  return (
    <EntityView
      entity={entity.data}
      error={entity.isError ? errorMessage(entity.error) : null}
    />
  );
}

type DocumentMentions = { id: string; title: string; mentions: EntityMention[] };

/** Passages grouped by document, keeping the API's order (by title, then position). */
export function groupByDocument(mentions: readonly EntityMention[]): DocumentMentions[] {
  const groups = new Map<string, DocumentMentions>();
  for (const mention of mentions) {
    const group = groups.get(mention.document_id) ?? {
      id: mention.document_id,
      title: mention.document_title,
      mentions: [],
    };
    group.mentions.push(mention);
    groups.set(mention.document_id, group);
  }
  return [...groups.values()];
}

export function EntityView({ entity, error }: { entity?: Entity; error?: string | null }) {
  const back = (
    <Link href="/graph" className="text-sm text-brand-600 hover:underline">
      ← Graph
    </Link>
  );
  if (error) {
    return (
      <div className="space-y-6">
        {back}
        <Alert>{error}</Alert>
      </div>
    );
  }
  if (!entity) {
    return (
      <div className="space-y-6">
        {back}
        <p aria-live="polite" className="text-sm text-slate-500">
          Loading…
        </p>
      </div>
    );
  }

  const style = entityType(entity.type);
  const documents = groupByDocument(entity.mentions);
  const passages = entity.mentions.length;
  const terms = [entity.name, ...entity.aliases.map((alias) => alias.name)].map((term) =>
    term.toLowerCase(),
  );

  return (
    <div className="space-y-6">
      {back}

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="break-words text-2xl font-semibold tracking-tight">{entity.name}</h1>
            <span className="inline-flex items-center gap-1.5 text-sm text-slate-600">
              <span aria-hidden="true" className={cx("size-2.5 rounded-full", style.dot)} />
              {style.label}
            </span>
          </div>
          <p className="text-sm text-slate-500">
            In {plural(passages, "passage", "passages")}
            {passages >= MENTION_LIMIT ? " or more" : ""} of{" "}
            {plural(documents.length, "document", "documents")}
          </p>
        </div>
        <Link
          href={searchUrl({ query: `"${entity.name}"`, mode: "fulltext" })}
          className={buttonClass("secondary")}
        >
          Search for it
        </Link>
      </div>

      {entity.aliases.length > 0 ? (
        <section aria-labelledby="aliases" className="space-y-2">
          <h2 id="aliases" className="text-sm font-medium text-slate-700">
            Also written as
          </h2>
          <ul className="flex flex-wrap gap-2">
            {entity.aliases.map((alias) => (
              <li
                key={alias.name}
                title={`Merged because the names are ${Math.round(alias.similarity * 100)}% similar`}
              >
                <Badge>{alias.name}</Badge>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <section aria-labelledby="mentions" className="space-y-3">
          <h2 id="mentions" className="text-sm font-medium text-slate-700">
            Mentioned in
          </h2>
          {documents.length === 0 ? (
            <Card className="text-sm text-slate-500">
              No passage mentions it any more; the document may have been changed.
            </Card>
          ) : (
            documents.map((document) => (
              <Card key={document.id} className="space-y-3 p-4">
                <Link
                  href={`/library/${document.id}`}
                  className="font-medium text-slate-900 hover:text-brand-700 hover:underline"
                >
                  {document.title}
                </Link>
                <ul className="space-y-2">
                  {document.mentions.map((mention) => (
                    <li key={mention.chunk_ordinal} className="space-y-1">
                      <p className="text-sm leading-relaxed text-slate-700">
                        {highlightSegments(mention.snippet, terms).map((segment, index) =>
                          segment.match ? (
                            <mark
                              key={index}
                              className="rounded bg-amber-100 px-0.5 text-slate-900"
                            >
                              {segment.text}
                            </mark>
                          ) : (
                            <span key={index}>{segment.text}</span>
                          ),
                        )}
                      </p>
                      <Link
                        href={`/library/${document.id}#chunk-${mention.chunk_ordinal}`}
                        className="text-xs text-brand-700 hover:underline"
                      >
                        Open passage {mention.chunk_ordinal + 1}
                        {mention.count > 1 ? ` · ${mention.count}×` : ""}
                      </Link>
                    </li>
                  ))}
                </ul>
              </Card>
            ))
          )}
        </section>

        <section aria-labelledby="related" className="space-y-3">
          <h2 id="related" className="text-sm font-medium text-slate-700">
            Related
          </h2>
          {entity.neighbours.length === 0 ? (
            <p className="text-sm text-slate-500">Not mentioned together with other entities.</p>
          ) : (
            <Card className="p-0">
              <ul className="divide-y divide-slate-100">
                {entity.neighbours.map((neighbour) => (
                  <li key={neighbour.id} className="px-4 py-2">
                    <Link
                      href={entityPath(neighbour.id)}
                      className="flex items-center gap-2 text-sm font-medium text-slate-900 hover:text-brand-700 hover:underline"
                    >
                      <span
                        aria-hidden="true"
                        className={cx("size-2 shrink-0 rounded-full", entityType(neighbour.type).dot)}
                      />
                      <span className="truncate">{neighbour.name}</span>
                    </Link>
                    <p className="pl-4 text-xs text-slate-500">
                      Together in {plural(neighbour.weight, "passage", "passages")}
                    </p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}
