"""Format parsers (run in-process here; production runs them in a child process)."""

import io
import zipfile

import pytest
from pypdf import PdfWriter

from knowvault.modules.ingestion.domain.model import ExtractionError, FailureCode
from knowvault.modules.ingestion.infrastructure import parsers
from knowvault.modules.ingestion.infrastructure.parsers import (
    ParseLimits,
    parse_document,
    parse_docx,
    parse_markdown,
    parse_pdf,
    parse_text,
)
from tests.factories import make_docx, make_pdf

LIMITS = ParseLimits(max_pages=50, max_chars=100_000)


def _code(exc: pytest.ExceptionInfo[ExtractionError]) -> FailureCode:
    return exc.value.code


class TestPdf:
    def test_extracts_text_per_page(self) -> None:
        result = parse_pdf(make_pdf(["First page (intro).", "Second page."]), LIMITS)
        assert result.page_count == 2
        assert [b.page for b in result.blocks] == [1, 2]
        assert "First page (intro)." in result.blocks[0].text
        assert "Second page." in result.blocks[1].text

    def test_pages_without_text_are_skipped_but_counted(self) -> None:
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        out = io.BytesIO()
        writer.write(out)
        result = parse_pdf(out.getvalue(), LIMITS)
        assert result.page_count == 1
        assert result.blocks == []

    def test_rejects_too_many_pages(self) -> None:
        with pytest.raises(ExtractionError) as exc:
            parse_pdf(make_pdf(["p"] * 3), ParseLimits(max_pages=2, max_chars=1000))
        assert _code(exc) is FailureCode.TOO_MANY_PAGES
        assert "3 pages" in exc.value.message

    def test_rejects_too_much_text(self) -> None:
        with pytest.raises(ExtractionError) as exc:
            parse_pdf(make_pdf(["x" * 200]), ParseLimits(max_pages=5, max_chars=100))
        assert _code(exc) is FailureCode.TEXT_TOO_LARGE

    def test_rejects_corrupt_pdf(self) -> None:
        with pytest.raises(ExtractionError) as exc:
            parse_pdf(b"%PDF-1.4\nthis is not really a pdf", LIMITS)
        assert _code(exc) is FailureCode.CORRUPT_FILE

    def test_rejects_password_protected_pdf(self) -> None:
        writer = PdfWriter(clone_from=io.BytesIO(make_pdf(["secret"])))
        try:
            writer.encrypt(user_password="pw", owner_password="owner", algorithm="RC4-128")
        except Exception as exc:  # pragma: no cover - depends on optional crypto backends
            pytest.skip(f"pypdf cannot encrypt here: {exc}")
        out = io.BytesIO()
        writer.write(out)
        with pytest.raises(ExtractionError) as exc_info:
            parse_pdf(out.getvalue(), LIMITS)
        assert _code(exc_info) is FailureCode.ENCRYPTED_PDF


class TestDocx:
    def test_tracks_headings_and_tables(self) -> None:
        data = make_docx(
            [
                ("Heading 1", "Intro"),
                (None, "Body one."),
                ("Heading 2", "Details"),
                (None, "Body two."),
                ("Heading 1", "Next"),
            ],
            table=[["Name", "Value"], ["a", "1"]],
        )
        result = parse_docx(data, LIMITS)
        assert [(b.heading_path, b.text) for b in result.blocks] == [
            (("Intro",), "Body one."),
            (("Intro", "Details"), "Body two."),
            (("Next",), "Name | Value\n\na | 1"),
        ]
        assert result.page_count is None

    def test_rejects_archives_that_expand_too_much(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(parsers, "_MAX_DOCX_UNCOMPRESSED", 1000)
        with pytest.raises(ExtractionError) as exc:
            parse_docx(make_docx([(None, "x" * 5000)]), LIMITS)
        assert _code(exc) is FailureCode.CORRUPT_FILE

    def test_rejects_zip_that_is_not_a_word_document(self) -> None:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("hello.txt", "hi")
        with pytest.raises(ExtractionError) as exc:
            parse_docx(out.getvalue(), LIMITS)
        assert _code(exc) is FailureCode.CORRUPT_FILE


class TestTextFormats:
    def test_markdown_headings_ignore_code_fences(self) -> None:
        source = b"# Guide\n\nIntro text\nwraps.\n\n## Setup\n```\n# not a heading\n```\n\nDone."
        result = parse_markdown(source, LIMITS)
        assert [(b.heading_path, b.text) for b in result.blocks] == [
            (("Guide",), "Intro text\nwraps."),
            (("Guide", "Setup"), "```\n# not a heading\n```"),
            (("Guide", "Setup"), "Done."),
        ]

    def test_markdown_sibling_heading_replaces_previous(self) -> None:
        result = parse_markdown(b"# A\n## B\nx\n## C\ny", LIMITS)
        assert [b.heading_path for b in result.blocks] == [("A", "B"), ("A", "C")]

    def test_plain_text_is_one_block(self) -> None:
        assert parse_text(b"Hello\n\nWorld", LIMITS).blocks[0].text == "Hello\n\nWorld"

    def test_invalid_utf8_is_rejected(self) -> None:
        with pytest.raises(ExtractionError) as exc:
            parse_text(b"\xff\xfe\x00bad", LIMITS)
        assert _code(exc) is FailureCode.CORRUPT_FILE

    def test_unknown_type_is_rejected(self) -> None:
        with pytest.raises(ExtractionError) as exc:
            parse_document(b"...", "image/png", LIMITS)
        assert _code(exc) is FailureCode.UNSUPPORTED_FILE_TYPE
