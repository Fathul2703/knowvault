"""ObjectStorage backed by a local directory (a Docker volume in Compose)."""

import asyncio
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from knowvault.core.storage import StoredObjectNotFoundError, validate_key


class FilesystemStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / validate_key(key)).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError(f"key escapes storage root: {key}")
        return path

    async def put_file(self, key: str, source: Path) -> None:
        target = self._path(key)

        def _copy() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temporary file in the same directory, then rename atomically, so a
            # crash never leaves a half-written object under the final name.
            fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
            try:
                with os.fdopen(fd, "wb") as out, source.open("rb") as src:
                    shutil.copyfileobj(src, out)
                os.replace(tmp_name, target)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise

        await asyncio.to_thread(_copy)

    async def read_bytes(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise StoredObjectNotFoundError(key) from exc

    async def iter_chunks(self, key: str, chunk_size: int = 64 * 1024) -> AsyncIterator[bytes]:
        path = self._path(key)
        try:
            handle = await asyncio.to_thread(path.open, "rb")
        except FileNotFoundError as exc:
            raise StoredObjectNotFoundError(key) from exc
        try:
            while chunk := await asyncio.to_thread(handle.read, chunk_size):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
