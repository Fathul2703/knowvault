"""Public interface of the library for the ingestion module.

Ingestion never touches the library's ORM models directly; it uses these functions, which run
inside the caller's session so they can share a transaction with the chunk writes.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core.errors import NotFoundError
from knowvault.modules.library.models import (
    KIND_NOTE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_READY,
    Document,
    Note,
)

PROCESS_DOCUMENT_JOB = "process_document"


@dataclass(frozen=True)
class ProcessingInput:
    document_id: uuid.UUID
    owner_id: uuid.UUID
    kind: str
    title: str
    mime_type: str
    content_version: int
    storage_key: str | None
    note_body: str | None


@dataclass(frozen=True)
class DocumentRef:
    id: uuid.UUID
    title: str
    kind: str
    status: str


async def ensure_owned(
    session: AsyncSession, owner_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentRef:
    """Returns the document if `owner_id` owns it; otherwise raises NotFoundError."""
    row = (
        await session.execute(
            select(Document.id, Document.title, Document.kind, Document.status).where(
                Document.id == document_id, Document.owner_id == owner_id
            )
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError("Document not found.")
    return DocumentRef(id=row.id, title=row.title, kind=row.kind, status=row.status)


async def start_processing(
    session: AsyncSession, document_id: uuid.UUID, content_version: int
) -> ProcessingInput | None:
    """Marks the document as processing and returns what the pipeline needs.

    Returns None when the document was deleted or has changed since the job was queued.
    Commits.
    """
    document = await session.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None or document.content_version != content_version:
        await session.commit()
        return None
    note_body = None
    if document.kind == KIND_NOTE:
        note_body = await session.scalar(
            select(Note.body_md).where(Note.document_id == document.id)
        )
    document.status = STATUS_PROCESSING
    document.error_code = None
    document.error_detail = None
    result = ProcessingInput(
        document_id=document.id,
        owner_id=document.owner_id,
        kind=document.kind,
        title=document.title,
        mime_type=document.mime_type,
        content_version=document.content_version,
        storage_key=document.storage_key,
        note_body=note_body,
    )
    await session.commit()
    return result


async def lock_current_version(
    session: AsyncSession, document_id: uuid.UUID, content_version: int
) -> bool:
    """Locks the document row; True if it still exists at `content_version`.

    Call at the start of the transaction that stores the processing results.
    """
    current = await session.scalar(
        select(Document.content_version).where(Document.id == document_id).with_for_update()
    )
    return current == content_version


async def mark_ready(
    session: AsyncSession, document_id: uuid.UUID, *, page_count: int | None
) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status=STATUS_READY, page_count=page_count, error_code=None, error_detail=None)
    )


async def mark_failed(
    session: AsyncSession,
    document_id: uuid.UUID,
    content_version: int,
    *,
    code: str,
    detail: str,
) -> None:
    """Records a failure, unless the document has changed since (a newer job will run)."""
    await session.execute(
        update(Document)
        .where(Document.id == document_id, Document.content_version == content_version)
        .values(status=STATUS_FAILED, error_code=code, error_detail=detail)
    )


async def mark_pending(session: AsyncSession, document_id: uuid.UUID, content_version: int) -> None:
    """Puts the document back in the queue state while a retry is scheduled."""
    await session.execute(
        update(Document)
        .where(Document.id == document_id, Document.content_version == content_version)
        .values(status=STATUS_PENDING)
    )
