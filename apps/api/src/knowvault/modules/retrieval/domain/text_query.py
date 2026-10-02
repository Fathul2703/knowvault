"""Turns a user query into web-search syntax for PostgreSQL full-text search.

`websearch_to_tsquery` joins words with AND. That suits deliberate keyword searches but means a
natural question ("How long are support conversations kept?") matches only chunks containing
every word, including "how" and "are" — in practice none (see ADR 0007). So:

* Queries using web-search syntax — "quoted phrases", -exclusions or OR — are passed through
  unchanged: the user asked for strict matching.
* Anything else is treated as a natural question: stop words are dropped and the remaining words
  are joined with OR, so a chunk matches if it contains any of them. Chunks are ranked first by
  how many distinct query words they contain (coordination level matching), then by ts_rank_cd;
  otherwise one word repeated often would beat a chunk that contains all of them.

Words are passed through whole (only surrounding punctuation is removed) so that PostgreSQL
tokenises them exactly as it tokenised the indexed text ("ERR_4711", "2.3.2", "read-only").
"""

import math
import re
from dataclasses import dataclass

# Common function words of English and Indonesian. Only words that carry little meaning on their
# own belong here; domain words ("data", "file", "baru") must stay searchable.
STOP_WORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "ada",
        "adalah",
        "agar",
        "akan",
        "aku",
        "anda",
        "apa",
        "apakah",
        "atau",
        "bagaimana",
        "bagi",
        "bahwa",
        "beberapa",
        "begitu",
        "belum",
        "berapa",
        "bisa",
        "boleh",
        "bukan",
        "dalam",
        "dan",
        "dapat",
        "dari",
        "daripada",
        "dengan",
        "di",
        "dia",
        "hanya",
        "harus",
        "ini",
        "itu",
        "jika",
        "juga",
        "kalau",
        "kami",
        "kamu",
        "kapan",
        "karena",
        "kami",
        "ke",
        "kenapa",
        "ketika",
        "kita",
        "lagi",
        "lah",
        "mana",
        "masih",
        "mereka",
        "mengapa",
        "nya",
        "oleh",
        "pada",
        "para",
        "per",
        "perlu",
        "saat",
        "saja",
        "sangat",
        "saya",
        "sebagai",
        "sebelum",
        "sedang",
        "sehingga",
        "sejak",
        "semua",
        "sendiri",
        "seperti",
        "setelah",
        "siapa",
        "sudah",
        "supaya",
        "tanpa",
        "telah",
        "tentang",
        "tersebut",
        "tetapi",
        "untuk",
        "yaitu",
        "yang",
    ]
)

_EDGE_PUNCTUATION = "\"'`.,;:!?()[]{}<>\u00ab\u00bb\u201c\u201d\u2018\u2019\u2026"
_WEB_SEARCH_SYNTAX = re.compile(r'"|(?:^|\s)-\S|(?:^|\s)OR(?:\s|$)')


def uses_web_search_syntax(query: str) -> bool:
    """True if the query contains a quoted phrase, a -word exclusion or an OR operator."""
    return bool(_WEB_SEARCH_SYNTAX.search(query))


@dataclass(frozen=True)
class FulltextQuery:
    # Web-search expression to match with (empty: nothing to search for).
    expression: str
    # Distinct words of a natural question, used to rank chunks by how many of them they
    # contain. Empty when the user wrote web-search syntax.
    terms: tuple[str, ...] = ()


# Bounds the per-term work for very long questions.
MAX_TERMS = 16
# A chunk must contain at least this share of a natural question's words ("minimum should
# match"). Sharing one incidental word is not evidence; without this, keyword hits on unrelated
# documents outvote the right semantic match in hybrid fusion (measured in ADR 0008).
MIN_MATCH_RATIO = 0.5


def minimum_match(terms: tuple[str, ...]) -> int:
    """How many distinct words of a natural question a chunk must contain."""
    return max(1, math.ceil(len(terms) * MIN_MATCH_RATIO)) if terms else 0


def fulltext_query(query: str) -> FulltextQuery:
    """The full-text query to run for `query`."""
    if uses_web_search_syntax(query):
        return FulltextQuery(expression=query)
    words = [w.strip(_EDGE_PUNCTUATION) for w in query.split()]
    words = [w for w in words if w]
    content = [w for w in words if w.casefold() not in STOP_WORDS]
    # A query made only of stop words still searches for them rather than for nothing.
    chosen = tuple(dict.fromkeys(content or words))[:MAX_TERMS]
    return FulltextQuery(expression=" OR ".join(chosen), terms=chosen)
