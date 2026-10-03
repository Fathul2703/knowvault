import type { Citation } from "@/lib/api/client";

/** `[1]`, `[2, 3]`: the citation markers answers use (same rule as the API). */
const MARKER = /\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\]/g;

type MdNode = {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: Record<string, unknown>;
};

function splitText(node: MdNode): MdNode[] {
  const text = node.value ?? "";
  const parts: MdNode[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) {
      parts.push({ type: "text", value: text.slice(last, start) });
    }
    const numbers = match[1].split(",").map((n) => n.trim());
    parts.push({
      type: "citation",
      data: {
        hName: "sup",
        hProperties: { dataCitation: numbers.join(",") },
        hChildren: [{ type: "text", value: match[0] }],
      },
    });
    last = start + match[0].length;
  }
  if (parts.length === 0) {
    return [node];
  }
  if (last < text.length) {
    parts.push({ type: "text", value: text.slice(last) });
  }
  return parts;
}

function transform(node: MdNode): void {
  if (!node.children) {
    return;
  }
  node.children = node.children.flatMap((child) => {
    if (child.type === "text") {
      return splitText(child);
    }
    transform(child);
    return [child];
  });
}

/**
 * Remark plugin: turns citation markers in text into `<sup data-citation="1,2">` elements.
 * Code is left alone (its text is not a `text` node).
 */
export function remarkCitations() {
  return (tree: MdNode) => transform(tree);
}

/** Source numbers an answer may link to: those of the sources it was given. */
export function sourceNumbers(citations: readonly Citation[]): Set<number> {
  return new Set(citations.map((c) => c.ordinal));
}

/** Source numbers that appear in the answer's text, ascending. */
export function citedInText(text: string): number[] {
  const numbers = new Set<number>();
  for (const match of text.matchAll(MARKER)) {
    for (const n of match[1].split(",")) {
      numbers.add(Number(n.trim()));
    }
  }
  return [...numbers].sort((a, b) => a - b);
}
