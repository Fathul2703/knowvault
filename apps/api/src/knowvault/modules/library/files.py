"""Receiving uploads: streaming to a temporary file and detecting the real file type."""

import codecs
import hashlib
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import UploadFile

MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_MARKDOWN = "text/markdown"
MIME_TEXT = "text/plain"

SUPPORTED_MIME_TYPES = (MIME_PDF, MIME_DOCX, MIME_MARKDOWN, MIME_TEXT)
_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
_TEXT_EXTENSIONS = {".txt"}

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class UploadTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class ReceivedFile:
    path: Path
    size_bytes: int
    sha256: str
    # True when the whole file decodes as UTF-8 and contains no NUL bytes.
    is_utf8_text: bool


async def receive_upload(upload: UploadFile, target: Path, *, max_bytes: int) -> ReceivedFile:
    """Copies the upload to `target`, hashing and inspecting it on the way."""
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    is_text = True
    size = 0
    with target.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise UploadTooLargeError
            digest.update(chunk)
            out.write(chunk)
            if is_text:
                try:
                    decoder.decode(chunk)
                    is_text = b"\x00" not in chunk
                except UnicodeDecodeError:
                    is_text = False
    if is_text:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            is_text = False
    return ReceivedFile(target, size, digest.hexdigest(), is_text and size > 0)


def _is_docx(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def detect_mime_type(received: ReceivedFile, filename: str) -> str | None:
    """Identifies the file from its content, never from the client's Content-Type.

    Plain text has no signature, so for UTF-8 text the extension decides between Markdown and
    plain text.
    """
    with received.path.open("rb") as handle:
        head = handle.read(8)
    if head.startswith(b"%PDF-"):
        return MIME_PDF
    if head.startswith(b"PK\x03\x04") and _is_docx(received.path):
        return MIME_DOCX
    if received.is_utf8_text:
        suffix = PurePosixPath(filename.lower()).suffix
        if suffix in _MARKDOWN_EXTENSIONS:
            return MIME_MARKDOWN
        if suffix in _TEXT_EXTENSIONS:
            return MIME_TEXT
    return None


def clean_filename(raw: str | None) -> str:
    """The base name of a client-supplied filename, without control characters."""
    name = PureWindowsPath(PurePosixPath(raw or "").name).name
    name = _CONTROL_CHARS.sub("", unicodedata.normalize("NFC", name)).strip()
    return name[:255] or "untitled"


def title_from_filename(filename: str) -> str:
    stem = PurePosixPath(filename).stem.strip() or filename
    return stem[:300]
