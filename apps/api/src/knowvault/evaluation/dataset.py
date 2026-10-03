"""Evaluation questions and relevance judgements.

Relevance is labelled with the source document and short evidence passages, not with chunk ids:
a retrieved chunk is relevant when it comes from that document and contains one of the
passages. Labels therefore stay valid when chunking changes.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = (
    "lexical",
    "paraphrase",
    "cross_lingual",
    "identifier",
    # Answerable from a document that also contains a prompt-injection attempt.
    "injection",
    # About an archived version of a document that has a current version with other numbers.
    "version",
    # About a document whose neighbour covers the same topic with other facts.
    "distractor",
    # The answer is one section of a long document.
    "long_document",
    "unanswerable",
)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    language: str
    category: str
    # Corpus file name holding the answer; None for questions the corpus cannot answer.
    document: str | None
    evidence: tuple[str, ...]
    # Injection questions: text that appears in an answer only if the model followed the
    # instructions planted in the document.
    canary: str | None = None

    @property
    def answerable(self) -> bool:
        return self.document is not None


class DatasetError(ValueError):
    pass


def normalize(text: str) -> str:
    """Case- and whitespace-insensitive form used to compare evidence with chunk text."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip().casefold()


def load_dataset(path: Path) -> list[Question]:
    questions: list[Question] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            question = Question(
                id=raw["id"],
                question=raw["question"],
                language=raw["language"],
                category=raw["category"],
                document=raw["document"],
                evidence=tuple(raw["evidence"]),
                canary=raw.get("canary"),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise DatasetError(f"{path.name}:{number}: invalid entry ({exc})") from exc
        if question.id in seen:
            raise DatasetError(f"{path.name}:{number}: duplicate id {question.id!r}")
        if question.category not in CATEGORIES:
            raise DatasetError(f"{path.name}:{number}: unknown category {question.category!r}")
        if (
            question.answerable != bool(question.evidence)
            or (question.category == "unanswerable") == question.answerable
        ):
            raise DatasetError(
                f"{path.name}:{number}: answerable questions need a document and evidence; "
                "unanswerable ones need neither"
            )
        if (question.category == "injection") != bool(question.canary):
            raise DatasetError(
                f"{path.name}:{number}: injection questions, and only they, need a canary"
            )
        seen.add(question.id)
        questions.append(question)
    return questions


def is_relevant(question: Question, document: str, content: str) -> bool:
    """True if the chunk `content` from corpus file `document` answers `question`."""
    if question.document != document:
        return False
    text = normalize(content)
    return any(normalize(passage) in text for passage in question.evidence)
