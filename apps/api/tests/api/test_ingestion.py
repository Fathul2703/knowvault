"""End to end: upload or write, run the worker, read the chunks."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from knowvault.core import jobs
from knowvault.core.config import Settings
from knowvault.core.db import Database
from knowvault.modules.library.models import Document
from knowvault.worker import build_pipeline, run_once
from tests.api.test_library import upload
from tests.conftest import RegisterFn
from tests.factories import make_docx, make_pdf

RunWorker = Callable[[], Awaitable[int]]


@pytest.fixture
def run_worker(settings: Settings, database: Database) -> RunWorker:
    """Processes queued jobs until the queue is empty; returns how many ran."""
    pipeline = build_pipeline(settings, database)

    async def _run() -> int:
        count = 0
        while await run_once(database, pipeline, settings):
            count += 1
        return count

    return _run


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register()
    return client


async def test_pdf_is_chunked_with_page_numbers(ada: AsyncClient, run_worker: RunWorker) -> None:
    pages = [
        "Chapter one introduces retrieval.\nIt continues on the next line.",
        "Page two talks about chunking.",
        "The final page concludes.",
    ]
    doc = (await upload(ada, "book.pdf", make_pdf(pages))).json()
    assert await run_worker() == 1

    processed = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
    assert processed["status"] == "ready"
    assert processed["page_count"] == 3
    assert processed["error_code"] is None

    chunks = (await ada.get(f"/api/v1/documents/{doc['id']}/chunks")).json()
    assert chunks["total"] == len(chunks["items"]) >= 1
    first = chunks["items"][0]
    assert first["ordinal"] == 0
    assert "Chapter one introduces retrieval." in first["content"]
    assert (first["page_start"], chunks["items"][-1]["page_end"]) == (1, 3)


async def test_docx_chunks_carry_headings(ada: AsyncClient, run_worker: RunWorker) -> None:
    data = make_docx([("Heading 1", "Methods"), (None, "We measured things carefully.")])
    doc = (await upload(ada, "paper.docx", data, "application/octet-stream")).json()
    await run_worker()
    [chunk] = (await ada.get(f"/api/v1/documents/{doc['id']}/chunks")).json()["items"]
    assert chunk["heading_path"] == ["Methods"]
    assert chunk["page_start"] is None


async def test_note_edit_replaces_chunks(ada: AsyncClient, run_worker: RunWorker) -> None:
    note = (
        await ada.post("/api/v1/notes", json={"title": "N", "body_md": "# Plan\n\nOld content."})
    ).json()
    await run_worker()
    first = (await ada.get(f"/api/v1/documents/{note['id']}/chunks")).json()["items"]
    assert first[0]["content"] == "Old content."
    assert first[0]["heading_path"] == ["Plan"]

    await ada.put(f"/api/v1/notes/{note['id']}", json={"title": "N", "body_md": "New content."})
    assert (await ada.get(f"/api/v1/documents/{note['id']}")).json()["status"] == "pending"
    await run_worker()
    second = (await ada.get(f"/api/v1/documents/{note['id']}/chunks")).json()
    assert [c["content"] for c in second["items"]] == ["New content."]
    assert (await ada.get(f"/api/v1/documents/{note['id']}")).json()["status"] == "ready"


async def test_document_without_text_fails_with_a_readable_reason(
    ada: AsyncClient, run_worker: RunWorker, database: Database
) -> None:
    doc = (await upload(ada, "scan.pdf", make_pdf(["   "]))).json()
    await run_worker()
    failed = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "no_extractable_text"
    assert "Scanned documents" in failed["error_detail"]
    async with database.sessionmaker() as session:
        job = await session.scalar(select(jobs.Job))
        assert job is not None
        assert job.status == jobs.FAILED  # permanent: not retried

    # A failed document can be queued again.
    retry = await ada.post(f"/api/v1/documents/{doc['id']}/reprocess")
    assert retry.status_code == 202
    assert retry.json()["status"] == "pending"
    assert retry.json()["error_code"] is None


async def test_corrupt_pdf_is_rejected_by_the_parser_process(
    ada: AsyncClient, run_worker: RunWorker
) -> None:
    broken = b"%PDF-1.4\n" + b"garbage " * 50
    doc = (await upload(ada, "broken.pdf", broken)).json()
    await run_worker()
    failed = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
    assert failed["error_code"] == "corrupt_file"


async def test_parser_timeout_fails_the_document(
    ada: AsyncClient, settings: Settings, database: Database
) -> None:
    doc = (await upload(ada, "slow.pdf", make_pdf(["x"]))).json()
    impatient = settings.model_copy(update={"parse_timeout_seconds": 0.001})
    pipeline = build_pipeline(impatient, database)
    assert await run_once(database, pipeline, impatient)
    failed = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
    assert failed["error_code"] == "parse_timeout"


async def test_missing_stored_file_fails_the_document(
    ada: AsyncClient, run_worker: RunWorker, settings: Settings
) -> None:
    doc = (await upload(ada)).json()
    for path in settings.storage_dir.rglob(doc["id"]):
        path.unlink()
    await run_worker()
    assert (await ada.get(f"/api/v1/documents/{doc['id']}")).json()["error_code"] == "file_missing"


async def test_results_for_an_outdated_version_are_discarded(
    ada: AsyncClient, settings: Settings, database: Database
) -> None:
    note = (await ada.post("/api/v1/notes", json={"title": "N", "body_md": "v1"})).json()
    pipeline = build_pipeline(settings, database)
    async with database.sessionmaker() as session:
        job = await jobs.claim(session, lock_timeout=jobs.backoff_for(10))
    assert job is not None
    # The note changes while the worker holds the job for version 1.
    async with database.sessionmaker() as session:
        await session.execute(
            update(Document).where(Document.id == job.resource_id).values(content_version=2)
        )
        await session.commit()
    await pipeline.process(job)
    chunks = (await ada.get(f"/api/v1/documents/{note['id']}/chunks")).json()
    assert chunks["total"] == 0


async def test_transient_errors_are_retried(
    ada: AsyncClient, settings: Settings, database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = (await upload(ada)).json()
    pipeline = build_pipeline(settings, database)

    async def flaky(*_: object, **__: object) -> None:
        raise ConnectionError("database hiccup")

    monkeypatch.setattr(pipeline._chunk_writer, "replace_chunks", flaky)
    assert await run_once(database, pipeline, settings)
    retrying = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
    assert retrying["status"] == "pending"
    async with database.sessionmaker() as session:
        job = await session.scalar(select(jobs.Job))
        assert job is not None
        assert job.status == jobs.QUEUED
        assert job.attempts == 1
        assert "database hiccup" in (job.last_error or "")
