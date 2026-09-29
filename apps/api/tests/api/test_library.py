"""Collections, uploads, documents and notes over HTTP."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select

from knowvault.core import jobs
from knowvault.core.config import Settings
from knowvault.core.db import Database
from tests.conftest import RegisterFn
from tests.factories import make_pdf

MakeInvite = Callable[[], Awaitable[str]]


async def upload(
    client: AsyncClient,
    name: str = "paper.pdf",
    data: bytes | None = None,
    content_type: str = "application/pdf",
    **fields: str,
) -> Response:
    return await client.post(
        "/api/v1/documents",
        files={"file": (name, make_pdf(["Hello"]) if data is None else data, content_type)},
        data=fields,
    )


async def queued_jobs(database: Database) -> list[jobs.Job]:
    async with database.sessionmaker() as session:
        return list(
            (await session.scalars(select(jobs.Job).where(jobs.Job.status == jobs.QUEUED))).all()
        )


@pytest.fixture
async def ada(client: AsyncClient, register: RegisterFn) -> AsyncClient:
    await register(email="ada@example.com")
    return client


@pytest.fixture
async def grace(app_client_factory: Callable[[], AsyncClient], make_invite: MakeInvite) -> Any:
    async with app_client_factory() as other:
        response = await other.post(
            "/api/v1/auth/register",
            json={
                "invite_code": await make_invite(),
                "email": "grace@example.com",
                "password": "another long password",
                "display_name": "Grace",
            },
        )
        assert response.status_code == 201
        yield other


class TestCollections:
    async def test_crud(self, ada: AsyncClient) -> None:
        created = await ada.post(
            "/api/v1/collections", json={"name": " Papers ", "description": ""}
        )
        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Papers"
        assert body["description"] is None
        assert body["document_count"] == 0

        renamed = await ada.patch(f"/api/v1/collections/{body['id']}", json={"name": "Research"})
        assert renamed.json()["name"] == "Research"

        listed = await ada.get("/api/v1/collections")
        assert [c["name"] for c in listed.json()] == ["Research"]

        deleted = await ada.delete(f"/api/v1/collections/{body['id']}")
        assert deleted.status_code == 204
        assert (await ada.get(f"/api/v1/collections/{body['id']}")).status_code == 404

    async def test_names_are_unique_per_user(self, ada: AsyncClient, grace: AsyncClient) -> None:
        assert (await ada.post("/api/v1/collections", json={"name": "Papers"})).status_code == 201
        duplicate = await ada.post("/api/v1/collections", json={"name": "Papers"})
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "collection_name_taken"
        # Another user may use the same name.
        assert (await grace.post("/api/v1/collections", json={"name": "Papers"})).status_code == 201

    async def test_document_count_and_delete_keeps_documents(self, ada: AsyncClient) -> None:
        collection = (await ada.post("/api/v1/collections", json={"name": "C"})).json()
        doc = (await upload(ada, collection_id=collection["id"])).json()
        assert doc["collection_id"] == collection["id"]
        got = (await ada.get(f"/api/v1/collections/{collection['id']}")).json()
        assert got["document_count"] == 1

        await ada.delete(f"/api/v1/collections/{collection['id']}")
        remaining = (await ada.get(f"/api/v1/documents/{doc['id']}")).json()
        assert remaining["collection_id"] is None


class TestUpload:
    async def test_pdf_is_stored_and_queued(
        self, ada: AsyncClient, database: Database, settings: Settings
    ) -> None:
        response = await upload(ada, "../My Paper.pdf", content_type="application/octet-stream")
        assert response.status_code == 202
        doc = response.json()
        assert doc["kind"] == "file"
        assert doc["status"] == "pending"
        assert doc["title"] == "My Paper"
        assert doc["original_filename"] == "My Paper.pdf"
        assert doc["mime_type"] == "application/pdf"

        [job] = await queued_jobs(database)
        assert str(job.resource_id) == doc["id"]
        assert job.payload == {"content_version": 1}
        stored = list(Path(settings.storage_dir).rglob("*"))
        assert any(p.is_file() and p.name == doc["id"] for p in stored)

    async def test_markdown_with_custom_title(self, ada: AsyncClient) -> None:
        response = await upload(
            ada, "notes.md", b"# Hello\n\nWorld", "text/markdown", title="  My notes "
        )
        assert response.status_code == 202
        assert response.json()["title"] == "My notes"
        assert response.json()["mime_type"] == "text/markdown"

    @pytest.mark.parametrize(
        ("name", "data"),
        [
            ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20),
            ("script.sh", b"echo hi"),
            ("fake.pdf", b"not a pdf at all"),
            ("empty.txt", b""),
        ],
    )
    async def test_rejects_unsupported_content(
        self, ada: AsyncClient, name: str, data: bytes
    ) -> None:
        response = await upload(ada, name, data, "application/pdf")
        assert response.status_code == 415
        assert response.json()["code"] == "unsupported_file_type"

    async def test_rejects_files_over_the_limit(self, ada: AsyncClient, database: Database) -> None:
        too_big = b"a" * (1024 * 1024 + 10)  # limit is 1 MB in tests
        response = await upload(ada, "big.txt", too_big, "text/plain")
        assert response.status_code == 413
        assert response.json()["code"] == "payload_too_large"
        assert await queued_jobs(database) == []

    async def test_rejects_the_same_file_twice(self, ada: AsyncClient, grace: AsyncClient) -> None:
        data = make_pdf(["Same content"])
        assert (await upload(ada, "a.pdf", data)).status_code == 202
        again = await upload(ada, "b.pdf", data)
        assert again.status_code == 409
        assert again.json()["code"] == "duplicate_document"
        # Deduplication is per user.
        assert (await upload(grace, "a.pdf", data)).status_code == 202

    async def test_rejects_foreign_origin_even_for_multipart(self, ada: AsyncClient) -> None:
        response = await ada.post(
            "/api/v1/documents",
            files={"file": ("a.pdf", make_pdf(["x"]), "application/pdf")},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403

    async def test_rejects_unknown_collection(self, ada: AsyncClient, grace: AsyncClient) -> None:
        other = (await grace.post("/api/v1/collections", json={"name": "Theirs"})).json()
        response = await upload(ada, collection_id=other["id"])
        assert response.status_code == 404


class TestDocuments:
    async def test_list_filters_and_paginates(self, ada: AsyncClient) -> None:
        for i in range(3):
            await upload(ada, f"doc{i}.pdf", make_pdf([f"Document {i}"]))
        await ada.post("/api/v1/notes", json={"title": "N", "body_md": "text"})

        first = (await ada.get("/api/v1/documents", params={"limit": 2})).json()
        assert [d["title"] for d in first["items"]] == ["N", "doc2"]
        second = (
            await ada.get("/api/v1/documents", params={"limit": 2, "cursor": first["next_cursor"]})
        ).json()
        assert [d["title"] for d in second["items"]] == ["doc1", "doc0"]
        assert second["next_cursor"] is None

        notes = (await ada.get("/api/v1/documents", params={"kind": "note"})).json()
        assert [d["kind"] for d in notes["items"]] == ["note"]

    async def test_invalid_cursor(self, ada: AsyncClient) -> None:
        response = await ada.get("/api/v1/documents", params={"cursor": "garbage"})
        assert response.status_code == 400

    async def test_update_title_and_collection(self, ada: AsyncClient) -> None:
        doc = (await upload(ada)).json()
        collection = (await ada.post("/api/v1/collections", json={"name": "C"})).json()
        moved = await ada.patch(
            f"/api/v1/documents/{doc['id']}",
            json={"title": "Renamed", "collection_id": collection["id"]},
        )
        assert moved.json()["title"] == "Renamed"
        assert moved.json()["collection_id"] == collection["id"]
        # Omitted fields are untouched; explicit null unassigns.
        unassigned = await ada.patch(f"/api/v1/documents/{doc['id']}", json={"collection_id": None})
        assert unassigned.json()["title"] == "Renamed"
        assert unassigned.json()["collection_id"] is None

    async def test_download_returns_the_original_file(self, ada: AsyncClient) -> None:
        data = make_pdf(["Download me"])
        doc = (await upload(ada, "Résumé 2026.pdf", data)).json()
        response = await ada.get(f"/api/v1/documents/{doc['id']}/file")
        assert response.status_code == 200
        assert response.content == data
        assert response.headers["content-type"] == "application/pdf"
        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert "filename*=UTF-8''R%C3%A9sum%C3%A9%202026.pdf" in disposition

    async def test_delete_removes_row_and_file(self, ada: AsyncClient, settings: Settings) -> None:
        doc = (await upload(ada)).json()
        assert (await ada.delete(f"/api/v1/documents/{doc['id']}")).status_code == 204
        assert (await ada.get(f"/api/v1/documents/{doc['id']}")).status_code == 404
        assert not [p for p in Path(settings.storage_dir).rglob(doc["id"]) if p.is_file()]

    async def test_reprocess_requires_a_finished_document(self, ada: AsyncClient) -> None:
        doc = (await upload(ada)).json()
        busy = await ada.post(f"/api/v1/documents/{doc['id']}/reprocess")
        assert busy.status_code == 409
        assert busy.json()["code"] == "document_busy"


class TestNotes:
    async def test_create_read_update(self, ada: AsyncClient, database: Database) -> None:
        created = await ada.post(
            "/api/v1/notes", json={"title": "Ideas", "body_md": "# Ideas\n\nFirst."}
        )
        assert created.status_code == 201
        note = created.json()
        assert note["kind"] == "note"
        assert note["body_md"] == "# Ideas\n\nFirst."
        assert note["status"] == "pending"

        fetched = await ada.get(f"/api/v1/notes/{note['id']}")
        assert fetched.json()["body_md"] == "# Ideas\n\nFirst."

        updated = await ada.put(
            f"/api/v1/notes/{note['id']}", json={"title": "Ideas v2", "body_md": "Second."}
        )
        assert updated.json()["title"] == "Ideas v2"
        assert updated.json()["body_md"] == "Second."
        # Both saves coalesce into one queued job carrying the latest version.
        [job] = await queued_jobs(database)
        assert job.payload == {"content_version": 2}

    async def test_title_only_change_does_not_reprocess(
        self, ada: AsyncClient, database: Database
    ) -> None:
        note = (await ada.post("/api/v1/notes", json={"title": "A", "body_md": "Body"})).json()
        async with database.sessionmaker() as session:
            job = await session.scalar(select(jobs.Job))
            assert job is not None
            job.status = jobs.SUCCEEDED
            await session.commit()
        await ada.put(f"/api/v1/notes/{note['id']}", json={"title": "B", "body_md": "Body"})
        assert await queued_jobs(database) == []

    async def test_limits(self, ada: AsyncClient, settings: Settings) -> None:
        empty = await ada.post("/api/v1/notes", json={"title": "A", "body_md": ""})
        assert empty.status_code == 422
        huge = "x" * (settings.max_note_chars + 1)
        too_long = await ada.post("/api/v1/notes", json={"title": "A", "body_md": huge})
        assert too_long.status_code == 413

    async def test_file_documents_are_not_notes(self, ada: AsyncClient) -> None:
        doc = (await upload(ada)).json()
        assert (await ada.get(f"/api/v1/notes/{doc['id']}")).status_code == 404


class TestIsolation:
    """Another user's resources behave as if they did not exist."""

    async def test_cross_user_access_is_not_found(
        self, ada: AsyncClient, grace: AsyncClient
    ) -> None:
        doc = (await upload(ada)).json()
        note = (await ada.post("/api/v1/notes", json={"title": "N", "body_md": "B"})).json()
        collection = (await ada.post("/api/v1/collections", json={"name": "C"})).json()

        requests = [
            grace.get(f"/api/v1/documents/{doc['id']}"),
            grace.patch(f"/api/v1/documents/{doc['id']}", json={"title": "x"}),
            grace.delete(f"/api/v1/documents/{doc['id']}"),
            grace.get(f"/api/v1/documents/{doc['id']}/file"),
            grace.get(f"/api/v1/documents/{doc['id']}/chunks"),
            grace.post(f"/api/v1/documents/{doc['id']}/reprocess"),
            grace.get(f"/api/v1/notes/{note['id']}"),
            grace.put(f"/api/v1/notes/{note['id']}", json={"title": "x", "body_md": "y"}),
            grace.get(f"/api/v1/collections/{collection['id']}"),
            grace.patch(f"/api/v1/collections/{collection['id']}", json={"name": "x"}),
            grace.delete(f"/api/v1/collections/{collection['id']}"),
        ]
        for request in requests:
            assert (await request).status_code == 404

        listing = (await grace.get("/api/v1/documents")).json()
        assert listing["items"] == []
        assert (await grace.get("/api/v1/collections")).json() == []
        # Ada's data is untouched.
        assert (await ada.get(f"/api/v1/documents/{doc['id']}")).json()["title"] == doc["title"]

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        for path in ("/api/v1/documents", "/api/v1/collections"):
            assert (await client.get(path)).status_code == 401
        assert (await upload(client)).status_code == 401
