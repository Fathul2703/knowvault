"""The Postgres job queue."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from knowvault.core import jobs
from knowvault.core.db import Database

LOCK = timedelta(minutes=10)


async def _enqueue(database: Database, resource: uuid.UUID, version: int = 1) -> None:
    async with database.sessionmaker() as session:
        await jobs.enqueue(
            session,
            type="test",
            resource_id=resource,
            payload={"version": version},
            max_attempts=2,
        )
        await session.commit()


async def _claim(database: Database, now: datetime | None = None) -> jobs.ClaimedJob | None:
    async with database.sessionmaker() as session:
        return await jobs.claim(session, lock_timeout=LOCK, now=now)


async def _all(database: Database) -> list[jobs.Job]:
    async with database.sessionmaker() as session:
        return list((await session.scalars(select(jobs.Job).order_by(jobs.Job.created_at))).all())


async def test_queued_jobs_for_the_same_resource_coalesce(database: Database) -> None:
    resource = uuid.uuid4()
    await _enqueue(database, resource, 1)
    await _enqueue(database, resource, 2)
    rows = await _all(database)
    assert len(rows) == 1
    assert rows[0].payload == {"version": 2}


async def test_enqueue_while_running_adds_a_second_job(database: Database) -> None:
    resource = uuid.uuid4()
    await _enqueue(database, resource, 1)
    assert await _claim(database) is not None
    await _enqueue(database, resource, 2)
    assert sorted(j.status for j in await _all(database)) == [jobs.QUEUED, jobs.RUNNING]


async def test_concurrent_claims_never_return_the_same_job(database: Database) -> None:
    for _ in range(5):
        await _enqueue(database, uuid.uuid4())
    claimed = await asyncio.gather(*(_claim(database) for _ in range(8)))
    ids = [job.id for job in claimed if job is not None]
    assert len(ids) == 5
    assert len(set(ids)) == 5


async def test_claim_increments_attempts_and_empty_queue_returns_none(database: Database) -> None:
    await _enqueue(database, uuid.uuid4())
    job = await _claim(database)
    assert job is not None
    assert job.attempts == 1
    assert job.payload == {"version": 1}
    assert await _claim(database) is None


async def test_retry_backs_off_then_dies(database: Database) -> None:
    await _enqueue(database, uuid.uuid4())
    job = await _claim(database)
    assert job is not None
    async with database.sessionmaker() as session:
        assert await jobs.schedule_retry(session, job, "boom")
        await session.commit()
    # Not runnable until the backoff has passed.
    assert await _claim(database) is None
    later = datetime.now(UTC) + jobs.backoff_for(1) + timedelta(seconds=1)
    second = await _claim(database, now=later)
    assert second is not None
    assert second.attempts == 2
    assert second.is_last_attempt
    async with database.sessionmaker() as session:
        assert not await jobs.schedule_retry(session, second, "boom again")
        await session.commit()
    [row] = await _all(database)
    assert row.status == jobs.DEAD
    assert row.last_error == "boom again"


async def test_retry_is_cancelled_when_a_newer_job_is_queued(database: Database) -> None:
    resource = uuid.uuid4()
    await _enqueue(database, resource, 1)
    job = await _claim(database)
    assert job is not None
    await _enqueue(database, resource, 2)
    async with database.sessionmaker() as session:
        await jobs.schedule_retry(session, job, "transient")
        await session.commit()
    statuses = {j.payload["version"]: j.status for j in await _all(database)}
    assert statuses == {1: jobs.CANCELLED, 2: jobs.QUEUED}


async def test_abandoned_running_job_is_claimed_again(database: Database) -> None:
    await _enqueue(database, uuid.uuid4())
    first = await _claim(database)
    assert first is not None
    assert await _claim(database) is None
    after_timeout = datetime.now(UTC) + LOCK + timedelta(seconds=1)
    again = await _claim(database, now=after_timeout)
    assert again is not None
    assert again.id == first.id
    assert again.attempts == 2


def test_backoff_grows_and_is_capped() -> None:
    assert [jobs.backoff_for(n).total_seconds() for n in (1, 2, 3)] == [10, 40, 160]
    assert jobs.backoff_for(20) == timedelta(hours=1)
