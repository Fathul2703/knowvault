"""Value types shared by the ingestion pipeline stages."""

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Block:
    """A run of text from the source with its location.

    `page` is the 1-based physical page for paginated formats (PDF) and None otherwise.
    `heading_path` lists the enclosing headings, outermost first.
    """

    text: str
    page: int | None = None
    heading_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class Extraction:
    blocks: list[Block]
    page_count: int | None = None


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    content: str
    char_start: int
    char_end: int
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...] = field(default_factory=tuple)


class FailureCode(StrEnum):
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    CORRUPT_FILE = "corrupt_file"
    ENCRYPTED_PDF = "encrypted_pdf"
    NO_EXTRACTABLE_TEXT = "no_extractable_text"
    TOO_MANY_PAGES = "too_many_pages"
    TEXT_TOO_LARGE = "text_too_large"
    PARSE_TIMEOUT = "parse_timeout"
    FILE_MISSING = "file_missing"
    PROCESSING_ERROR = "processing_error"


_MESSAGES = {
    FailureCode.UNSUPPORTED_FILE_TYPE: "This file type is not supported.",
    FailureCode.CORRUPT_FILE: "The file could not be read. It may be damaged or malformed.",
    FailureCode.ENCRYPTED_PDF: "The PDF is password-protected. Upload an unprotected copy.",
    FailureCode.NO_EXTRACTABLE_TEXT: (
        "No text could be extracted. Scanned documents (images of text) are not supported yet."
    ),
    FailureCode.TOO_MANY_PAGES: "The document has more pages than the current limit.",
    FailureCode.TEXT_TOO_LARGE: "The document contains more text than the current limit.",
    FailureCode.PARSE_TIMEOUT: "Reading the document took too long.",
    FailureCode.FILE_MISSING: "The uploaded file could not be found. Upload it again.",
    FailureCode.PROCESSING_ERROR: "Processing failed after several attempts. Try again later.",
}


class ExtractionError(Exception):
    """A permanent problem with the document itself; retrying will not help."""

    def __init__(self, code: FailureCode, detail: str | None = None) -> None:
        super().__init__(detail or _MESSAGES[code])
        self.code = code
        self.message = detail or _MESSAGES[code]


def failure_message(code: FailureCode) -> str:
    return _MESSAGES[code]
