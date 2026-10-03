"""HTTP endpoints for collections, documents and notes."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from knowvault.core.db import SessionDep
from knowvault.core.deps import SettingsDep, StorageDep
from knowvault.core.errors import NotFoundError, Problem
from knowvault.core.storage import StoredObjectNotFoundError
from knowvault.modules.identity.dependencies import CurrentUser, user_rate_limit
from knowvault.modules.library.models import Document, Note
from knowvault.modules.library.schemas import (
    CollectionCreate,
    CollectionOut,
    CollectionUpdate,
    DocumentKind,
    DocumentOut,
    DocumentPage,
    DocumentStatus,
    DocumentUpdate,
    NoteCreate,
    NoteOut,
    NoteUpdate,
)
from knowvault.modules.library.service import CollectionWithCount, LibraryService

# Multipart endpoint: exempt from the JSON-only rule and subject to the upload size limit.
UPLOAD_PATH = "/api/v1/documents"

router = APIRouter(prefix="/api/v1")

# Uploads, note saves and reprocessing all queue parsing and embedding work.
_DOCUMENT_WRITES = [
    user_rate_limit(
        "document_writes",
        lambda settings: settings.document_writes_per_hour,
        timedelta(hours=1),
        "Too many uploads or note saves in the last hour. Try again later.",
    )
]

_ERRORS: dict[int | str, dict[str, object]] = {
    code: {"model": Problem, "content": {"application/problem+json": {}}}
    for code in (400, 401, 403, 404, 409, 413, 415, 422, 429)
}


def get_library_service(
    session: SessionDep, settings: SettingsDep, storage: StorageDep
) -> LibraryService:
    return LibraryService(session, settings, storage)


Library = Annotated[LibraryService, Depends(get_library_service)]


def _collection_out(item: CollectionWithCount) -> CollectionOut:
    c = item.collection
    return CollectionOut(
        id=c.id,
        name=c.name,
        description=c.description,
        document_count=item.document_count,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _note_out(document: Document, note: Note) -> NoteOut:
    return NoteOut.model_validate(
        {**DocumentOut.model_validate(document).model_dump(), "body_md": note.body_md}
    )


# --- Collections -----------------------------------------------------------------------------


@router.get("/collections", response_model=list[CollectionOut], tags=["collections"])
async def list_collections(user: CurrentUser, library: Library) -> list[CollectionOut]:
    return [_collection_out(c) for c in await library.list_collections(user.id)]


@router.post(
    "/collections",
    response_model=CollectionOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    tags=["collections"],
)
async def create_collection(
    body: CollectionCreate, user: CurrentUser, library: Library
) -> CollectionOut:
    item = await library.create_collection(user.id, name=body.name, description=body.description)
    return _collection_out(item)


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionOut,
    responses=_ERRORS,
    tags=["collections"],
)
async def get_collection(
    collection_id: uuid.UUID, user: CurrentUser, library: Library
) -> CollectionOut:
    return _collection_out(await library.get_collection(user.id, collection_id))


@router.patch(
    "/collections/{collection_id}",
    response_model=CollectionOut,
    responses=_ERRORS,
    tags=["collections"],
)
async def update_collection(
    collection_id: uuid.UUID, body: CollectionUpdate, user: CurrentUser, library: Library
) -> CollectionOut:
    item = await library.update_collection(
        user.id, collection_id, changes=body.model_dump(exclude_unset=True)
    )
    return _collection_out(item)


@router.delete(
    "/collections/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    tags=["collections"],
)
async def delete_collection(
    collection_id: uuid.UUID, user: CurrentUser, library: Library
) -> Response:
    """Deletes the collection. Its documents are kept and become unassigned."""
    await library.delete_collection(user.id, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Documents -------------------------------------------------------------------------------


@router.get("/documents", response_model=DocumentPage, responses=_ERRORS, tags=["documents"])
async def list_documents(
    user: CurrentUser,
    library: Library,
    collection_id: uuid.UUID | None = None,
    kind: DocumentKind | None = None,
    status: DocumentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> DocumentPage:
    """Lists documents, newest first."""
    items, next_cursor = await library.list_documents(
        user.id,
        collection_id=collection_id,
        kind=kind,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return DocumentPage(
        items=[DocumentOut.model_validate(d) for d in items], next_cursor=next_cursor
    )


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    tags=["documents"],
    dependencies=_DOCUMENT_WRITES,
)
async def upload_document(
    user: CurrentUser,
    library: Library,
    file: Annotated[UploadFile, File(description="PDF, DOCX, Markdown or plain text")],
    title: Annotated[str | None, Form(max_length=300)] = None,
    collection_id: Annotated[uuid.UUID | None, Form()] = None,
) -> DocumentOut:
    """Stores a file and queues it for processing. Poll the document for its status."""
    document = await library.upload(
        user.id,
        file,
        title=title.strip() if title and title.strip() else None,
        collection_id=collection_id,
    )
    return DocumentOut.model_validate(document)


@router.get(
    "/documents/{document_id}", response_model=DocumentOut, responses=_ERRORS, tags=["documents"]
)
async def get_document(document_id: uuid.UUID, user: CurrentUser, library: Library) -> DocumentOut:
    return DocumentOut.model_validate(await library.get_document(user.id, document_id))


@router.patch(
    "/documents/{document_id}", response_model=DocumentOut, responses=_ERRORS, tags=["documents"]
)
async def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, user: CurrentUser, library: Library
) -> DocumentOut:
    document = await library.update_document(
        user.id,
        document_id,
        title=body.title,
        collection_id=body.collection_id,
        fields_set=body.model_fields_set,
    )
    return DocumentOut.model_validate(document)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    tags=["documents"],
)
async def delete_document(document_id: uuid.UUID, user: CurrentUser, library: Library) -> Response:
    """Deletes the document, its extracted content and its stored file."""
    await library.delete_document(user.id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    tags=["documents"],
    dependencies=_DOCUMENT_WRITES,
)
async def reprocess_document(
    document_id: uuid.UUID, user: CurrentUser, library: Library
) -> DocumentOut:
    """Queues the document for processing again, e.g. after a failure."""
    return DocumentOut.model_validate(await library.reprocess(user.id, document_id))


def _content_disposition(filename: str) -> str:
    fallback = filename.encode("ascii", "replace").decode().replace('"', "").replace("?", "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get(
    "/documents/{document_id}/file",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/octet-stream": {}}}, **_ERRORS},
    tags=["documents"],
)
async def download_document(
    document_id: uuid.UUID, user: CurrentUser, library: Library, storage: StorageDep
) -> StreamingResponse:
    """Downloads the original uploaded file. Always served as an attachment."""
    document = await library.get_document(user.id, document_id)
    if document.storage_key is None:
        raise NotFoundError("This document has no uploaded file.")
    chunks = storage.iter_chunks(document.storage_key)
    try:
        first = await anext(chunks)
    except StopAsyncIteration:
        first = b""
    except StoredObjectNotFoundError as exc:
        raise NotFoundError("The stored file is missing.") from exc

    async def body() -> AsyncIterator[bytes]:
        yield first
        async for chunk in chunks:
            yield chunk

    return StreamingResponse(
        body(),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": _content_disposition(
                document.original_filename or document.title
            ),
            "Content-Length": str(document.size_bytes),
        },
    )


# --- Notes -----------------------------------------------------------------------------------


@router.post(
    "/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    tags=["notes"],
    dependencies=_DOCUMENT_WRITES,
)
async def create_note(body: NoteCreate, user: CurrentUser, library: Library) -> NoteOut:
    document, note = await library.create_note(
        user.id, title=body.title, body_md=body.body_md, collection_id=body.collection_id
    )
    return _note_out(document, note)


@router.get("/notes/{document_id}", response_model=NoteOut, responses=_ERRORS, tags=["notes"])
async def get_note(document_id: uuid.UUID, user: CurrentUser, library: Library) -> NoteOut:
    return _note_out(*await library.get_note(user.id, document_id))


@router.put(
    "/notes/{document_id}",
    response_model=NoteOut,
    responses=_ERRORS,
    tags=["notes"],
    dependencies=_DOCUMENT_WRITES,
)
async def update_note(
    document_id: uuid.UUID, body: NoteUpdate, user: CurrentUser, library: Library
) -> NoteOut:
    """Replaces the note's title and body. A changed body is processed again."""
    document, note = await library.update_note(
        user.id, document_id, title=body.title, body_md=body.body_md
    )
    return _note_out(document, note)
