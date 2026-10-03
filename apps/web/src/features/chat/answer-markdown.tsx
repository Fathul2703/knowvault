"use client";

import type { Root } from "mdast";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { remarkCitations } from "./citations";

const citationPlugin = remarkCitations as unknown as () => (tree: Root) => void;

/**
 * Renders an answer's Markdown. Raw HTML in the answer is shown as text, never rendered, and
 * `[n]` becomes a link to source n only when the answer was given a source n.
 */
export function AnswerMarkdown({
  text,
  sources,
  onCite,
}: {
  text: string;
  sources: ReadonlySet<number>;
  onCite: (ordinal: number) => void;
}) {
  const components: Components = {
    sup: ({ children, ...props }) => {
      const value = (props as Record<string, unknown>)["data-citation"];
      if (typeof value !== "string") {
        return <sup>{children}</sup>;
      }
      return (
        <>
          {value.split(",").map((part) => {
            const ordinal = Number(part);
            return sources.has(ordinal) ? (
              <button
                key={part}
                type="button"
                onClick={() => onCite(ordinal)}
                aria-label={`Show source ${ordinal}`}
                className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded bg-brand-50 px-1 align-baseline text-[0.7rem] font-semibold leading-none text-brand-700 hover:bg-brand-100"
              >
                {ordinal}
              </button>
            ) : (
              // A number the answer was not given a source for: shown, but not as a link.
              <span key={part} className="text-slate-400" title="No such source">
                [{ordinal}]
              </span>
            );
          })}
        </>
      );
    },
    // Unsafe URLs (e.g. javascript:) arrive empty: show their text without a link.
    a: ({ href, children }) =>
      href ? (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      ) : (
        <span>{children}</span>
      ),
  };

  return (
    <div className="answer text-sm leading-relaxed text-slate-800">
      <ReactMarkdown remarkPlugins={[remarkGfm, citationPlugin]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
