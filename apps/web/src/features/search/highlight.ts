/** Client-side helpers for showing why a search result matched. Pure functions. */

// Letters and digits in any script, plus underscores (so codes like ERR_4711 stay whole).
const WORD = /[\p{L}\p{N}_]+/gu;
// Web-search operators that are not words to highlight.
const OPERATORS = new Set(["or"]);

/**
 * The words of a query worth highlighting: lower-cased, unique, at least two characters,
 * without `OR` and without words excluded with a leading `-`.
 */
export function queryTerms(query: string): string[] {
  const terms = new Set<string>();
  for (const raw of query.split(/\s+/)) {
    if (raw.startsWith("-")) {
      continue;
    }
    for (const word of raw.match(WORD) ?? []) {
      const term = word.toLowerCase();
      if (term.length >= 2 && !OPERATORS.has(term)) {
        terms.add(term);
      }
    }
  }
  return [...terms];
}

export type Segment = { text: string; match: boolean };

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function termPattern(terms: readonly string[]): RegExp | null {
  if (terms.length === 0) {
    return null;
  }
  // Longest first, so "timeout" wins over "time" when both are terms.
  const alternatives = [...terms].sort((a, b) => b.length - a.length).map(escapeRegExp);
  return new RegExp(`(${alternatives.join("|")})`, "giu");
}

/** Splits text into plain and matching segments. Rendered as text nodes, never as HTML. */
export function highlightSegments(text: string, terms: readonly string[]): Segment[] {
  const pattern = termPattern(terms);
  if (!pattern) {
    return text ? [{ text, match: false }] : [];
  }
  return text
    .split(pattern)
    .filter((part) => part !== "")
    .map((part) => ({ text: part, match: terms.includes(part.toLowerCase()) }));
}

export type Snippet = { text: string; clippedStart: boolean; clippedEnd: boolean };

/**
 * A window of about `maxLength` characters, starting a little before the first match so the
 * reader sees why the passage was returned. Cuts at spaces where possible.
 */
export function makeSnippet(text: string, terms: readonly string[], maxLength = 320): Snippet {
  if (text.length <= maxLength) {
    return { text, clippedStart: false, clippedEnd: false };
  }
  const pattern = termPattern(terms);
  const firstMatch = pattern ? text.search(pattern) : -1;
  let start = firstMatch > 0 ? Math.max(0, firstMatch - Math.floor(maxLength / 4)) : 0;
  if (start > 0) {
    const space = text.indexOf(" ", start);
    start = space !== -1 && space < firstMatch ? space + 1 : start;
  }
  let end = Math.min(text.length, start + maxLength);
  if (end < text.length) {
    const space = text.lastIndexOf(" ", end);
    end = space > start ? space : end;
  }
  return { text: text.slice(start, end), clippedStart: start > 0, clippedEnd: end < text.length };
}
