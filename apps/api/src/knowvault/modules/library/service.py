"""Library use cases: collections, uploads, notes, listing and deletion."""

import base64
import binascii
import logging
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import Select, and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knowvault.core import jobs
from knowvault.core.config import Settings
from knowvault.core.errors import AppError, ConflictError, NotFoundError
from knowvault.core.storage import ObjectStorage
from knowvault.modules.library.files import (
    UploadTooLargeError,
    clean_filename,
    detect_mime_type,
    receive_upload,
    title_from_filename,
)
from knowvault.modules.library.models import (
    KIND_FILE,
    KIND_NOTE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    Collection,
    Document,
    Note,
)
from knowvault.modules.library.processing import PROCESS_DOCUMENT_JOB

logger = logging.getLogger(__name__)


class CollectionNameTakenError(ConflictError):
    code = "collection_name_taken"
    title = "A collection with this name already exists"


class DuplicateDocumentError(ConflictError):
    code = "duplicate_document"
    title = "This file is already in your library"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"
    title = "Unsupported file type"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    title = "Payload too large"


class DocumentBusyError(ConflictError):
    code = "document_busy"
    title = "The document is already being processed"


@dataclass(frozen=True)
class CollectionWithCount:
    collection: Collection
    document_count: int


def _encode_cursor(document: Document) -> str:
    raw = f"{document.created_at.isoformat()}|{document.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        created, doc_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(created), uuid.UUID(doc_id)
    except (ValueError, binascii.Error) as exc:
        raise AppError("The cursor is invalid.") from exc


class LibraryService:
    def __init__(self, session: AsyncSession, settings: Settings, storage: ObjectStorage) -> None:
        self._db = session
        self._settings = settings
        self._storage = storage

    # --- Collections ---------------------------------------------------------------------

    def _collections_with_counts(self, owner_id: uuid.UUID) -> Select[Collection, int]:
        count = (
            select(func.count(Document.id))
            .where(Document.collection_id == Collection.id)
            .correlate(Collection)
            .scalar_subquery()
        )
        return select(Collection, count).where(Collection.owner_id == owner_id)

    async def list_collections(self, owner_id: uuid.UUID) -> list[CollectionWithCount]:
        rows = await self._db.execute(
            self._collections_with_counts(owner_id).order_by(func.lower(Collection.name))
        )
        return [CollectionWithCount(collection, count) for collection, count in rows]

    async def get_collection(
        self, owner_id: uuid.UUID, collection_id: uuid.UUID
    ) -> CollectionWithCount:
        row = (
            await self._db.execute(
                self._collections_with_counts(owner_id).where(Collection.id == collection_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Collection not found.")
        collection, count = row
        return CollectionWithCount(collection, count)

    async def _owned_collection(self, owner_id: uuid.UUID, collection_id: uuid.UUID) -> Collection:
        collection = await self._db.scalar(
            select(Collection).where(
                Collection.id == collection_id, Collection.owner_id == owner_id
            )
        )
        if collection is None:
            raise NotFoundError("Collection not found.")
        return collection

    async def _commit_collection(self) -> None:
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise CollectionNameTakenError from exc

    async def create_collection(
        self, owner_id: uuid.UUID, *, name: str, description: str | None
    ) -> CollectionWithCount:
        collection = Collection(owner_id=owner_id, name=name, description=description or None)
        self._db.add(collection)
        await self._commit_collection()
        return CollectionWithCount(collection, 0)

    async def update_collection(
        self,
        owner_id: uuid.UUID,
        collection_id: uuid.UUID,
        *,
        changes: dict[str, str | None],
    ) -> CollectionWithCount:
        collection = await self._owned_collection(owner_id, collection_id)
        if "name" in changes and changes["name"] is not None:
            collection.name = changes["name"]
        if "description" in changes:
            collection.description = changes["description"] or None
        await self._commit_collection()
        return await self.get_collection(owner_id, collection_id)

    async def delete_collection(self, owner_id: uuid.UUID, collection_id: uuid.UUID) -> None:
        """Deletes the collection. Its documents stay in the library, without a collection."""
        collection = await self._owned_collection(owner_id, collection_id)
        await self._db.delete(collection)
        await self._db.commit()

    # --- Documents -----------------------------------------------------------------------

    async def _owned_document(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self._db.scalar(
            select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
        )
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def get_document(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        return await self._owned_document(owner_id, document_id)

    async def list_documents(
        self,
        owner_id: uuid.UUID,
        *,
        collection_id: uuid.UUID | None,
        kind: str | None,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[Sequence[Document], str | None]:
        query = select(Document).where(Document.owner_id == owner_id)
        if collection_id is not None:
            query = query.where(Document.collection_id == collection_id)
        if kind is not None:
            query = query.where(Document.kind == kind)
        if status is not None:
            query = query.where(Document.status == status)
        if cursor is not None:
            created, doc_id = _decode_cursor(cursor)
            query = query.where(
                or_(
                    Document.created_at < created,
                    and_(Document.created_at == created, Document.id < doc_id),
                )
            )
        rows = (
            await self._db.scalars(
                query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
            )
        ).all()
        if len(rows) > limit:
            return rows[:limit], _encode_cursor(rows[limit - 1])
        return rows, None

    async def _enqueue_processing(self, document: Document) -> None:
        await jobs.enqueue(
            self._db,
            type=PROCESS_DOCUMENT_JOB,
            resource_id=document.id,
            payload={"content_version": document.content_version},
            max_attempts=self._settings.job_max_attempts,
        )

    async def upload(
        self,
        owner_id: uuid.UUID,
        upload: UploadFile,
        *,
        title: str | None,
        collection_id: uuid.UUID | None,
    ) -> Document:
        if collection_id is not None:
            await self._owned_collection(owner_id, collection_id)
        filename = clean_filename(upload.filename)

        with tempfile.TemporaryDirectory(prefix="knowvault-upload-") as tmp:
            try:
                received = await receive_upload(
                    upload, Path(tmp) / "upload", max_bytes=self._settings.max_upload_bytes
                )
            except UploadTooLargeError as exc:
                raise PayloadTooLargeError(
                    f"The upload limit is {self._settings.max_upload_mb} MB."
                ) from exc
            if received.size_bytes == 0:
                raise UnsupportedFileTypeError("The file is empty.")
            mime_type = detect_mime_type(received, filename)
            if mime_type is None:
                raise UnsupportedFileTypeError(
                    "Upload a PDF, Word (.docx), Markdown (.md) or text (.txt) file."
                )

            existing = await self._db.scalar(
                select(Document.title).where(
                    Document.owner_id == owner_id,
                    Document.kind == KIND_FILE,
                    Document.sha256 == received.sha256,
                )
            )
            if existing is not None:
                raise DuplicateDocumentError(f"The same file is already stored as “{existing}”.")

            document_id = uuid.uuid4()
            storage_key = f"users/{owner_id}/documents/{document_id}"
            document = Document(
                id=document_id,
                owner_id=owner_id,
                collection_id=collection_id,
                kind=KIND_FILE,
                title=title or title_from_filename(filename),
                mime_type=mime_type,
                original_filename=filename,
                storage_key=storage_key,
                size_bytes=received.size_bytes,
                sha256=received.sha256,
                status=STATUS_PENDING,
                content_version=1,
            )
            # Store the file before the row exists, so a worker never sees a document
            # without its content. If the insert fails, remove the file again.
            await self._storage.put_file(storage_key, received.path)

        self._db.add(document)
        await self._db.flush()
        await self._enqueue_processing(document)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            await self._storage.delete(storage_key)
            raise DuplicateDocumentError from exc
        logger.info(
            "document_uploaded",
            extra={"document_id": str(document.id), "mime_type": mime_type},
        )
        return document

    async def update_document(
        self,
        owner_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        title: str | None,
        collection_id: uuid.UUID | None,
        fields_set: set[str],
    ) -> Document:
        document = await self._owned_document(owner_id, document_id)
        if "title" in fields_set and title is not None:
            document.title = title
        if "collection_id" in fields_set:
            if collection_id is not None:
                await self._owned_collection(owner_id, collection_id)
            document.collection_id = collection_id
        await self._db.commit()
        await self._db.refresh(document)
        return document

    async def delete_document(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> None:
        """Deletes the document with its chunks, then its stored file."""
        document = await self._owned_document(owner_id, document_id)
        storage_key = document.storage_key
        await self._db.execute(delete(Document).where(Document.id == document.id))
        await self._db.commit()
        if storage_key is not None:
            try:
                await self._storage.delete(storage_key)
            except OSError:
                # The database is the source of truth; an orphaned file is only wasted space.
                logger.warning(
                    "stored_file_not_deleted",
                    extra={"document_id": str(document_id)},
                    exc_info=True,
                )

    async def reprocess(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        document = await self._owned_document(owner_id, document_id)
        if document.status in (STATUS_PENDING, STATUS_PROCESSING):
            raise DocumentBusyError
        document.status = STATUS_PENDING
        document.error_code = None
        document.error_detail = None
        await self._enqueue_processing(document)
        await self._db.commit()
        await self._db.refresh(document)
        return document

    # --- Notes ---------------------------------------------------------------------------

    def _check_note_length(self, body: str) -> None:
        if len(body) > self._settings.max_note_chars:
            raise PayloadTooLargeError(
                f"Notes are limited to {self._settings.max_note_chars:,} characters."
            )

    async def create_note(
        self,
        owner_id: uuid.UUID,
        *,
        title: str,
        body_md: str,
        collection_id: uuid.UUID | None,
    ) -> tuple[Document, Note]:
        self._check_note_length(body_md)
        if collection_id is not None:
            await self._owned_collection(owner_id, collection_id)
        document = Document(
            owner_id=owner_id,
            collection_id=collection_id,
            kind=KIND_NOTE,
            title=title,
            mime_type="text/markdown",
            size_bytes=len(body_md.encode()),
            status=STATUS_PENDING,
            content_version=1,
        )
        self._db.add(document)
        await self._db.flush()
        note = Note(document_id=document.id, body_md=body_md)
        self._db.add(note)
        await self._enqueue_processing(document)
        await self._db.commit()
        await self._db.refresh(document)
        return document, note

    async def get_note(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Document, Note]:
        row = (
            await self._db.execute(
                select(Document, Note)
                .join(Note, Note.document_id == Document.id)
                .where(Document.id == document_id, Document.owner_id == owner_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Note not found.")
        document, note = row
        return document, note

    async def update_note(
        self, owner_id: uuid.UUID, document_id: uuid.UUID, *, title: str, body_md: str
    ) -> tuple[Document, Note]:
        self._check_note_length(body_md)
        document, note = await self.get_note(owner_id, document_id)
        document.title = title
        if note.body_md != body_md:
            note.body_md = body_md
            document.size_bytes = len(body_md.encode())
            document.content_version += 1
            document.status = STATUS_PENDING
            document.error_code = None
            document.error_detail = None
            await self._enqueue_processing(document)
        await self._db.commit()
        await self._db.refresh(document)
        return document, note
