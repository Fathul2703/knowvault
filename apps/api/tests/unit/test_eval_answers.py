"""Answer evaluation metrics, review sampling and the review tally."""

import json
from pathlib import Path

import pytest

from knowvault.evaluation.answers import AnswerResult, CitedSource, review_sample, summarize_answers
from knowvault.evaluation.dataset import DatasetError, load_dataset
from knowvault.evaluation.review import format_tally, tally_review


def result(
    question_id: str,
    status: str,
    *,
    answerable: bool = True,
    cited: tuple[int, ...] = (),
    invalid: tuple[int, ...] = (),
    relevant: bool = False,
    leaked: bool | None = None,
    category: str = "lexical",
) -> AnswerResult:
    source = CitedSource(1, "doc.md", None, "text", cited=1 in cited, relevant=relevant)
    return AnswerResult(
        question_id=question_id,
        category=category if answerable else "unanswerable",
        language="en",
        answerable=answerable,
        status=status,
        answer="answer",
        cited=cited,
        invalid_citations=invalid,
        sources=(source,),
        latency_ms=100.0,
        input_tokens=50,
        output_tokens=10,
        canary_leaked=leaked,
    )


def test_summary_separates_decisions_citations_and_leaks() -> None:
    summary = summarize_answers(
        [
            result("a1", "complete", cited=(1,), relevant=True),
            result("a2", "complete", cited=(1,), invalid=(4,)),
            result("a3", "refused", relevant=True),
            result("a4", "error"),
            result("i1", "complete", leaked=True, category="injection"),
            result("u1", "refused", answerable=False),
            result("u2", "complete", answerable=False),
        ]
    )
    assert summary.answered_rate == 3 / 5
    assert summary.false_refusal_rate == 1 / 5
    assert summary.refusal_rate == 0.5
    assert summary.false_answer_rate == 0.5
    # a1, a2, i1 answered and u1 refused: 4 right decisions of 7.
    assert summary.refusal_accuracy == 4 / 7
    assert summary.error_rate == 1 / 7
    assert summary.answers == 4
    assert summary.with_citation_rate == 2 / 4
    assert summary.invalid_citation_rate == 1 / 4
    assert summary.cited_relevant_rate == 1 / 3
    assert summary.evidence_in_sources_rate == 2 / 5
    assert (summary.injection_questions, summary.injection_leaks) == (1, 1)
    assert summary.input_tokens == 350
    assert summary.by_category["unanswerable"]["cited_relevant"] is None
    assert summary.by_category["lexical"]["answered"] == 2 / 4


def test_summary_without_unanswerable_questions_has_no_refusal_rate() -> None:
    summary = summarize_answers([result("a1", "complete")])
    assert summary.refusal_rate is None
    assert summary.false_answer_rate is None


def test_review_sample_is_reproducible_and_only_answered_questions() -> None:
    rows = [result(f"a{i}", "complete") for i in range(40)] + [result("r", "refused")]
    first = review_sample(rows, 30)
    assert len(first) == 30
    assert first == review_sample(rows, 30)
    assert all(r.status == "complete" for r in first)
    assert len(review_sample(rows[:5], 30)) == 5


SHEET = """# Answer review

## 1. `a1` · lexical · en

- [x] [1] supports
- [ ] [1] partly
- [ ] [1] does not support
- [ ] [2] supports
- [x] [2] partly
- [ ] [2] does not support

- [x] faithful
- [ ] partly faithful
- [ ] unfaithful

## 2. `a2` · lexical · en

- [x] [1] supports
- [X] [1] does not support

- [ ] faithful
- [ ] partly faithful
- [ ] unfaithful
"""


def test_tally_counts_marks_and_flags_incomplete_sections() -> None:
    tally = tally_review(SHEET)
    assert tally.answers == 2
    assert tally.citations == {"supports": 1, "partly": 1, "does not support": 0}
    assert tally.overall == {"faithful": 1, "partly faithful": 0, "unfaithful": 0}
    assert tally.incomplete == [2]
    text = format_tally(tally)
    assert "supports: 1 (50%)" in text
    assert "Incomplete (unmarked or marked twice): 2" in text


def write(tmp_path: Path, entry: dict[str, object]) -> Path:
    path = tmp_path / "questions.jsonl"
    path.write_text(json.dumps(entry) + "\n")
    return path


def test_injection_questions_need_a_canary(tmp_path: Path) -> None:
    entry: dict[str, object] = {
        "id": "x",
        "question": "q",
        "language": "en",
        "category": "injection",
        "document": "d.md",
        "evidence": ["e"],
    }
    with pytest.raises(DatasetError, match="canary"):
        load_dataset(write(tmp_path, entry))
    entry["canary"] = "PWNED"
    assert load_dataset(write(tmp_path, entry))[0].canary == "PWNED"
    with pytest.raises(DatasetError, match="canary"):
        load_dataset(write(tmp_path, {**entry, "category": "lexical"}))
