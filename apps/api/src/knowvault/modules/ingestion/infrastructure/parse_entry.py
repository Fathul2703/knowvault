"""Entry point of the parser child process.

Protocol: the document bytes arrive on stdin; one JSON object is written to stdout:
`{"ok": true, "page_count": ..., "blocks": [...]}` or `{"ok": false, "code": ..., "message": ...}`.
Usage: python -m knowvault.modules.ingestion.infrastructure.parse_entry \
    MIME MAX_PAGES MAX_CHARS MEMORY_MB
"""

import json
import sys

from knowvault.modules.ingestion.domain.model import ExtractionError, FailureCode
from knowvault.modules.ingestion.infrastructure.parsers import ParseLimits, parse_document


def _limit_memory(megabytes: int) -> None:
    try:
        import resource

        limit = megabytes * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        # Not enforceable on every platform (e.g. macOS); the timeout still applies.
        pass


def main(argv: list[str]) -> int:
    mime_type, max_pages, max_chars, memory_mb = argv
    _limit_memory(int(memory_mb))
    data = sys.stdin.buffer.read()
    limits = ParseLimits(max_pages=int(max_pages), max_chars=int(max_chars))
    try:
        extraction = parse_document(data, mime_type, limits)
        result: dict[str, object] = {
            "ok": True,
            "page_count": extraction.page_count,
            "blocks": [
                {"text": b.text, "page": b.page, "heading_path": list(b.heading_path)}
                for b in extraction.blocks
            ],
        }
    except ExtractionError as exc:
        result = {"ok": False, "code": exc.code.value, "message": exc.message}
    except MemoryError:
        result = {
            "ok": False,
            "code": FailureCode.CORRUPT_FILE.value,
            "message": "The document is too complex to process.",
        }
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
