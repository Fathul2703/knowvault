"""Source selection, citation checks and NO_ANSWER detection."""

import uuid

import pytest

from knowvault.modules.assistant.domain.citations import check_citations, strip_citations
from knowvault.modules.assistant.domain.context import select_sources
from knowvault.modules.assistant.domain.model import Passage
from knowvault.modules.assistant.domain.refusal import RefusalDetector, mentions_no_answer

DOC_A = uuid.uuid4()
DOC_B = uuid.uuid4()


def passage(content: str, document: uuid.UUID = DOC_A, ordinal: int = 0) -> Passage:
    return Passage(uuid.uuid4(), document, "Title", ordinal, content)


class TestSelectSources:
    def test_numbers_sources_from_one(self) -> None:
        sources = select_sources(
            [passage("a"), passage("b", ordinal=1)], max_sources=8, max_chars=100
        )
        assert [s.ordinal for s in sources] == [1, 2]

    def test_groups_by_document_in_order_of_best_passage(self) -> None:
        ranked = [
            passage("b2", DOC_B, ordinal=2),
            passage("a5", DOC_A, ordinal=5),
            passage("b0", DOC_B, ordinal=0),
            passage("a1", DOC_A, ordinal=1),
        ]
        sources = select_sources(ranked, max_sources=8, max_chars=100)
        assert [s.passage.content for s in sources] == ["b0", "b2", "a1", "a5"]

    def test_respects_source_limit_in_relevance_order(self) -> None:
        ranked = [passage("first"), passage("second"), passage("third")]
        sources = select_sources(ranked, max_sources=2, max_chars=100)
        assert {s.passage.content for s in sources} == {"first", "second"}

    def test_skips_passages_over_budget_but_keeps_shorter_later_ones(self) -> None:
        ranked = [passage("x" * 60), passage("y" * 60), passage("z" * 30)]
        sources = select_sources(ranked, max_sources=8, max_chars=100)
        assert [len(s.passage.content) for s in sources] == [60, 30]

    def test_skips_duplicate_text(self) -> None:
        ranked = [passage("Same  text"), passage("same text", DOC_B), passage("other")]
        assert len(select_sources(ranked, max_sources=8, max_chars=100)) == 2

    def test_empty(self) -> None:
        assert select_sources([], max_sources=8, max_chars=100) == []


class TestLocation:
    def test_pdf_pages(self) -> None:
        one = Passage(uuid.uuid4(), DOC_A, "T", 0, "c", page_start=3, page_end=3)
        many = Passage(uuid.uuid4(), DOC_A, "T", 0, "c", page_start=3, page_end=4)
        assert one.location == "p. 3"
        assert many.location == "pp. 3\u20134"

    def test_heading_path_or_nothing(self) -> None:
        headed = Passage(uuid.uuid4(), DOC_A, "T", 0, "c", heading_path=("Leave", "Holidays"))
        assert headed.location == "Leave > Holidays"
        assert passage("c").location is None


class TestCitations:
    @pytest.mark.parametrize(
        ("text", "cited", "invalid"),
        [
            ("Leave is 12 days [1].", (1,), ()),
            ("Both [2][1] and [2, 3].", (1, 2, 3), ()),
            ("Wrong [4] and [0].", (), (0, 4)),
            ("No markers.", (), ()),
            ("Not a citation: [a] or [ 1 ]x", (), ()),
        ],
    )
    def test_check(self, text: str, cited: tuple[int, ...], invalid: tuple[int, ...]) -> None:
        result = check_citations(text, source_count=3)
        assert result.cited == cited
        assert result.invalid == invalid

    def test_strip(self) -> None:
        assert strip_citations("Leave is 12 days [1]. Ask HR [2, 3].") == (
            "Leave is 12 days. Ask HR."
        )


def run(detector: RefusalDetector, pieces: list[str]) -> str:
    shown = "".join(detector.feed(piece) for piece in pieces)
    return shown + detector.finish()


class TestRefusalDetector:
    def test_marker_split_across_tokens_is_hidden(self) -> None:
        detector = RefusalDetector()
        assert run(detector, ["NO", "_ANS", "WER"]) == ""
        assert detector.refused

    def test_marker_with_leading_whitespace_and_trailing_text(self) -> None:
        detector = RefusalDetector()
        assert run(detector, ["\n ", "NO_ANSWER", ".", " Sorry"]) == ""
        assert detector.refused

    def test_answer_passes_through_once_it_cannot_be_the_marker(self) -> None:
        detector = RefusalDetector()
        assert detector.feed("N") == ""
        assert detector.feed("o leave") == "No leave"
        assert detector.feed(" days.") == " days."
        assert detector.finish() == ""
        assert not detector.refused

    def test_short_answer_that_is_a_marker_prefix_is_released_at_the_end(self) -> None:
        detector = RefusalDetector()
        assert run(detector, ["NO"]) == "NO"
        assert not detector.refused

    def test_empty_reply_is_a_refusal(self) -> None:
        detector = RefusalDetector()
        assert run(detector, ["  "]) == ""
        assert detector.refused

    def test_marker_after_text(self) -> None:
        assert mentions_no_answer("I am not sure. NO_ANSWER")
        assert not mentions_no_answer("No answer was given by HR.")
