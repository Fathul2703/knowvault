"""Upload type detection and filename handling."""

from pathlib import Path

import pytest

from knowvault.modules.ingestion.infrastructure import parsers
from knowvault.modules.library import files
from knowvault.modules.library.files import (
    ReceivedFile,
    clean_filename,
    detect_mime_type,
    title_from_filename,
)
from tests.factories import make_docx, make_pdf


def _received(tmp_path: Path, data: bytes, *, text: bool) -> ReceivedFile:
    path = tmp_path / "upload"
    path.write_bytes(data)
    return ReceivedFile(path=path, size_bytes=len(data), sha256="x", is_utf8_text=text)


@pytest.mark.parametrize(
    ("data", "is_text", "filename", "expected"),
    [
        (make_pdf(["hi"]), False, "report.docx", files.MIME_PDF),  # content wins over name
        (make_docx([(None, "hi")]), False, "notes.pdf", files.MIME_DOCX),
        (b"# Title", True, "notes.md", files.MIME_MARKDOWN),
        (b"# Title", True, "notes.MARKDOWN", files.MIME_MARKDOWN),
        (b"plain", True, "notes.txt", files.MIME_TEXT),
        (b"plain", True, "script.sh", None),  # text, but not an accepted extension
        (b"PK\x03\x04not really a zip", False, "a.docx", None),
        (b"\x89PNG\r\n\x1a\n", False, "image.pdf", None),
    ],
)
def test_detects_type_from_content(
    tmp_path: Path, data: bytes, is_text: bool, filename: str, expected: str | None
) -> None:
    assert detect_mime_type(_received(tmp_path, data, text=is_text), filename) == expected


def test_library_and_parser_agree_on_supported_types() -> None:
    assert set(files.SUPPORTED_MIME_TYPES) == set(parsers.SUPPORTED_MIME_TYPES)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\thesis.docx", "thesis.docx"),
        ("bad\x00name\n.md", "badname.md"),
        ("", "untitled"),
        (None, "untitled"),
    ],
)
def test_clean_filename(raw: str | None, expected: str) -> None:
    assert clean_filename(raw) == expected


def test_title_from_filename() -> None:
    assert title_from_filename("Attention Is All You Need.pdf") == "Attention Is All You Need"
    assert title_from_filename(".md") == ".md"
