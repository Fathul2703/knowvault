"""Format-specific text extraction.

These functions run inside a separate, resource-limited process (see `subprocess_parser`),
because they parse untrusted files with third-party libraries.
"""

import io
import re
import zipfile
from dataclasses import dataclass

from knowvault.modules.ingestion.domain.model import (
    Block,
    Extraction,
    ExtractionError,
    FailureCode,
)

MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_MARKDOWN = "text/markdown"
MIME_TEXT = "text/plain"

# A .docx is a ZIP archive; refuse archives that would expand to an unreasonable size.
_MAX_DOCX_UNCOMPRESSED = 200 * 1024 * 1024
_MAX_DOCX_ENTRIES = 10_000

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_FENCE = re.compile(r"^\s*(```|~~~)")
_DOCX_HEADING_STYLE = re.compile(r"^heading\s*([1-9])$", re.IGNORECASE)


@dataclass(frozen=True)
class ParseLimits:
    max_pages: int
    max_chars: int


class _TextBudget:
    def __init__(self, max_chars: int) -> None:
        self.remaining = max_chars

    def spend(self, text: str) -> None:
        self.remaining -= len(text)
        if self.remaining < 0:
            raise ExtractionError(FailureCode.TEXT_TOO_LARGE)


def parse_pdf(data: bytes, limits: ParseLimits) -> Extraction:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
            except Exception as exc:
                raise ExtractionError(FailureCode.ENCRYPTED_PDF) from exc
            if not decrypted:
                raise ExtractionError(FailureCode.ENCRYPTED_PDF)
        page_count = len(reader.pages)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(FailureCode.CORRUPT_FILE) from exc

    if page_count > limits.max_pages:
        raise ExtractionError(
            FailureCode.TOO_MANY_PAGES,
            f"The document has {page_count} pages; the limit is {limits.max_pages}.",
        )

    budget = _TextBudget(limits.max_chars)
    blocks = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            # One unreadable page should not discard the rest of the document.
            text = ""
        budget.spend(text)
        if text.strip():
            blocks.append(Block(text=text, page=number))
    return Extraction(blocks=blocks, page_count=page_count)


def _docx_heading_level(style_name: str) -> int | None:
    if style_name.strip().lower() == "title":
        return 1
    match = _DOCX_HEADING_STYLE.match(style_name.strip())
    return int(match.group(1)) if match else None


def parse_docx(data: bytes, limits: ParseLimits) -> Extraction:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ExtractionError(FailureCode.CORRUPT_FILE) from exc
    if (
        len(entries) > _MAX_DOCX_ENTRIES
        or sum(e.file_size for e in entries) > _MAX_DOCX_UNCOMPRESSED
    ):
        raise ExtractionError(FailureCode.CORRUPT_FILE, "The file expands to an unsafe size.")

    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
        budget = _TextBudget(limits.max_chars)
        blocks: list[Block] = []
        headings: list[str] = []
        for element in document.element.body.iterchildren():
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "p":
                paragraph = Paragraph(element, document)
                text = paragraph.text
                budget.spend(text)
                style = paragraph.style.name if paragraph.style is not None else ""
                level = _docx_heading_level(style or "")
                if level is not None and text.strip():
                    headings = [*headings[: level - 1], text.strip()]
                elif text.strip():
                    blocks.append(Block(text=text, heading_path=tuple(headings)))
            elif tag == "tbl":
                table = Table(element, document)
                rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
                text = "\n\n".join(r for r in rows if r.strip(" |"))
                budget.spend(text)
                if text:
                    blocks.append(Block(text=text, heading_path=tuple(headings)))
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(FailureCode.CORRUPT_FILE) from exc
    return Extraction(blocks=blocks)


def _decode(data: bytes, limits: ParseLimits) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(
            FailureCode.CORRUPT_FILE, "The file is not valid UTF-8 text."
        ) from exc
    _TextBudget(limits.max_chars).spend(text)
    return text


def parse_markdown(data: bytes, limits: ParseLimits) -> Extraction:
    """Splits Markdown into paragraphs and tracks ATX headings (`#`, `##`, ...)."""
    blocks: list[Block] = []
    headings: list[str] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block(text="\n".join(paragraph), heading_path=tuple(headings)))
            paragraph.clear()

    for line in _decode(data, limits).splitlines():
        if _MD_FENCE.match(line):
            in_fence = not in_fence
            paragraph.append(line)
            continue
        heading = None if in_fence else _MD_HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings = [*headings[: level - 1], heading.group(2)]
        elif not line.strip() and not in_fence:
            flush()
        else:
            paragraph.append(line)
    flush()
    return Extraction(blocks=blocks)


def parse_text(data: bytes, limits: ParseLimits) -> Extraction:
    return Extraction(blocks=[Block(text=_decode(data, limits))])


_PARSERS = {
    MIME_PDF: parse_pdf,
    MIME_DOCX: parse_docx,
    MIME_MARKDOWN: parse_markdown,
    MIME_TEXT: parse_text,
}

SUPPORTED_MIME_TYPES = frozenset(_PARSERS)


def parse_document(data: bytes, mime_type: str, limits: ParseLimits) -> Extraction:
    parser = _PARSERS.get(mime_type)
    if parser is None:
        raise ExtractionError(FailureCode.UNSUPPORTED_FILE_TYPE)
    return parser(data, limits)
