"""The committed evaluation corpus and dataset stay consistent with each other and the chunker.

If chunking parameters change and split an evidence passage across chunks, this fails, so the
labels are fixed before an evaluation silently reports false misses.
"""

import importlib.util
from collections import Counter
from pathlib import Path

import pytest

from knowvault.evaluation.dataset import DatasetError, is_relevant, load_dataset, normalize
from knowvault.modules.ingestion.domain.chunking import chunk_blocks
from knowvault.modules.ingestion.domain.normalize import normalize_blocks
from knowvault.modules.ingestion.infrastructure.parsers import (
    ParseLimits,
    parse_markdown,
    parse_pdf,
)

EVAL_DIR = Path(__file__).resolve().parents[4] / "eval"
CORPUS = EVAL_DIR / "corpus"
DATASET = EVAL_DIR / "datasets" / "retrieval.jsonl"
LIMITS = ParseLimits(max_pages=500, max_chars=5_000_000)


def corpus_documents() -> list[Path]:
    return sorted(p for p in CORPUS.iterdir() if p.suffix in (".md", ".pdf"))


def chunks_of(path: Path) -> list[str]:
    """The chunks the production pipeline creates for a corpus file."""
    parse = parse_pdf if path.suffix == ".pdf" else parse_markdown
    blocks = normalize_blocks(parse(path.read_bytes(), LIMITS).blocks)
    return [chunk.content for chunk in chunk_blocks(blocks)]


@pytest.fixture(scope="module")
def questions() -> list:  # type: ignore[type-arg]
    return load_dataset(DATASET)


def test_dataset_size_and_balance(questions: list) -> None:  # type: ignore[type-arg]
    categories = Counter(q.category for q in questions)
    assert sum(1 for q in questions if q.answerable) >= 50
    assert categories["unanswerable"] >= 5
    assert {"lexical", "paraphrase", "cross_lingual", "identifier"} <= set(categories)
    assert {q.language for q in questions} == {"en", "id"}


def test_every_corpus_document_is_asked_about(questions: list) -> None:  # type: ignore[type-arg]
    asked = Counter(q.document for q in questions if q.answerable)
    files = {p.name for p in corpus_documents()}
    assert set(asked) <= files, "dataset refers to missing corpus files"
    assert all(asked[name] >= 2 for name in files), "every document needs at least 2 questions"


def test_every_evidence_passage_lies_within_one_chunk(questions: list) -> None:  # type: ignore[type-arg]
    chunks = {p.name: chunks_of(p) for p in corpus_documents()}
    problems = []
    for question in questions:
        if not question.answerable:
            continue
        assert question.document is not None
        if not any(
            is_relevant(question, question.document, chunk) for chunk in chunks[question.document]
        ):
            problems.append(question.id)
    assert problems == [], f"evidence not found inside a single chunk: {problems}"


def test_relevance_requires_the_labelled_document(questions: list) -> None:  # type: ignore[type-arg]
    question = next(q for q in questions if q.answerable)
    content = " ".join(question.evidence)
    assert is_relevant(question, question.document or "", content.upper())
    assert not is_relevant(question, "another-file.md", content)


def test_normalize_ignores_case_and_whitespace() -> None:
    assert normalize("  Hello\n  WORLD ") == "hello world"


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ('{"id": "a"}', "invalid entry"),
        (
            '{"id": "a", "question": "q", "language": "en", "category": "other", '
            '"document": "d.md", "evidence": ["x"]}',
            "unknown category",
        ),
        (
            '{"id": "a", "question": "q", "language": "en", "category": "lexical", '
            '"document": null, "evidence": []}',
            "answerable questions need",
        ),
    ],
)
def test_loader_rejects_invalid_entries(tmp_path: Path, line: str, message: str) -> None:
    path = tmp_path / "d.jsonl"
    path.write_text(line + "\n")
    with pytest.raises(DatasetError, match=message):
        load_dataset(path)


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    entry = (
        '{"id": "a", "question": "q", "language": "en", "category": "lexical", '
        '"document": "d.md", "evidence": ["x"]}'
    )
    path = tmp_path / "d.jsonl"
    path.write_text(f"{entry}\n{entry}\n")
    with pytest.raises(DatasetError, match="duplicate id"):
        load_dataset(path)


def test_committed_pdfs_match_their_sources() -> None:
    """eval/corpus/*.pdf are built from eval/corpus-src/*.txt; rebuild them after editing."""
    spec = importlib.util.spec_from_file_location(
        "build_pdf_corpus", EVAL_DIR / "tools" / "build_pdf_corpus.py"
    )
    assert spec is not None
    assert spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    sources = sorted((EVAL_DIR / "corpus-src").glob("*.txt"))
    assert sources
    for source in sources:
        built = builder.make_pdf(source.read_text(encoding="utf-8"))
        assert (CORPUS / f"{source.stem}.pdf").read_bytes() == built, (
            f"{source.stem}.pdf is out of date: run python eval/tools/build_pdf_corpus.py"
        )
