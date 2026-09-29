"""DocumentParser that runs the parsers in a child process with a timeout and memory limit.

A malicious or pathological file can make a parser loop forever or exhaust memory. Running it
in a separate process means the worker can always kill it and carry on with the next job.
"""

import asyncio
import json
import logging
import sys

from knowvault.modules.ingestion.domain.model import (
    Block,
    Extraction,
    ExtractionError,
    FailureCode,
)
from knowvault.modules.ingestion.infrastructure.parsers import SUPPORTED_MIME_TYPES

logger = logging.getLogger(__name__)

_ENTRY_MODULE = "knowvault.modules.ingestion.infrastructure.parse_entry"


class ParserCrashedError(RuntimeError):
    """The child process died without an answer. Treated as transient and retried."""


class SubprocessDocumentParser:
    def __init__(
        self, *, max_pages: int, max_chars: int, timeout_seconds: float, memory_mb: int
    ) -> None:
        self._args = [str(max_pages), str(max_chars), str(memory_mb)]
        self._timeout = timeout_seconds

    async def parse(self, data: bytes, mime_type: str) -> Extraction:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise ExtractionError(FailureCode.UNSUPPORTED_FILE_TYPE)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            _ENTRY_MODULE,
            mime_type,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(data), self._timeout)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise ExtractionError(FailureCode.PARSE_TIMEOUT) from exc

        try:
            result = json.loads(stdout)
        except ValueError:
            result = None
        if process.returncode != 0 or not isinstance(result, dict):
            logger.warning(
                "parser_process_failed",
                extra={"returncode": process.returncode, "stderr": stderr.decode()[-2000:]},
            )
            raise ParserCrashedError(f"parser exited with code {process.returncode}")

        if not result.get("ok"):
            raise ExtractionError(FailureCode(result["code"]), result.get("message"))
        return Extraction(
            blocks=[
                Block(text=b["text"], page=b["page"], heading_path=tuple(b["heading_path"]))
                for b in result["blocks"]
            ],
            page_count=result["page_count"],
        )
