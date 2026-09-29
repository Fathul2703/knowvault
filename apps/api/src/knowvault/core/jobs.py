"""A small job queue stored in PostgreSQL.

Workers claim jobs with `FOR UPDATE SKIP LOCKED`, so several workers never pick the same job.
Jobs are generic (`type` + `resource_id`); enqueueing the same type and resource while a job is
still queued updates that job instead of adding another, so bursts of edits coalesce into one run.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    and_,
    case,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, aliased, mapped_column

from knowvault.core.db import Base, TimestampMixin

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"  # permanent failure, not retried
DEAD = "dead"  # retries exhausted
CANCELLED = "cancelled"  # superseded by a newer job for the same resource

JOB_STATUSES = (QUEUED, RUNNING, SUCCEEDED, FAILED, DEAD, CANCELLED)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead', 'cancelled')",
            name="status",
        ),
        # At most one queued job per (type, resource): new requests coalesce into it.
        Index(
            "uq_jobs_queued_resource",
            "type",
            "resource_id",
            unique=True,
            postgresql_where=text("status = 'queued'"),
        ),
        Index("ix_jobs_claimable", "run_after", postgresql_where=text("status = 'queued'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    type: str
    resource_id: uuid.UUID
    payload: dict[str, Any]
    attempts: int
    max_attempts: int

    @property
    def is_last_attempt(self) -> bool:
        return self.attempts >= self.max_attempts


def _now() -> datetime:
    return datetime.now(UTC)


async def enqueue(
    session: AsyncSession,
    *,
    type: str,
    resource_id: uuid.UUID,
    payload: dict[str, Any],
    max_attempts: int,
) -> None:
    """Adds a job, or refreshes the payload of the job already queued for this resource.

    Runs inside the caller's transaction, so the job exists only if the caller commits.
    """
    statement = (
        insert(Job)
        .values(
            id=uuid.uuid4(),
            type=type,
            resource_id=resource_id,
            payload=payload,
            status=QUEUED,
            attempts=0,
            max_attempts=max_attempts,
            run_after=func.now(),
        )
        .on_conflict_do_update(
            index_elements=[Job.type, Job.resource_id],
            index_where=text("status = 'queued'"),
            set_={"payload": payload, "updated_at": func.now()},
        )
    )
    await session.execute(statement)


async def claim(
    session: AsyncSession, *, lock_timeout: timedelta, now: datetime | None = None
) -> ClaimedJob | None:
    """Claims the next runnable job and commits, or returns None if there is nothing to do.

    Jobs left `running` by a worker that died are claimed again after `lock_timeout`.
    """
    now = now or _now()
    candidate = (
        select(Job.id)
        .where(
            or_(
                and_(Job.status == QUEUED, Job.run_after <= now),
                and_(Job.status == RUNNING, Job.locked_at < now - lock_timeout),
            )
        )
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            update(Job)
            .where(Job.id == candidate)
            .values(status=RUNNING, attempts=Job.attempts + 1, locked_at=now, updated_at=now)
            .returning(
                Job.id, Job.type, Job.resource_id, Job.payload, Job.attempts, Job.max_attempts
            )
        )
    ).one_or_none()
    await session.commit()
    if row is None:
        return None
    return ClaimedJob(
        id=row.id,
        type=row.type,
        resource_id=row.resource_id,
        payload=row.payload,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
    )


async def mark_succeeded(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Marks the job done. Runs in the caller's transaction."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=SUCCEEDED, locked_at=None, last_error=None, updated_at=func.now())
    )


async def mark_failed(session: AsyncSession, job_id: uuid.UUID, error: str) -> None:
    """Marks the job permanently failed (no retry). Runs in the caller's transaction."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=FAILED, locked_at=None, last_error=error[:2000], updated_at=func.now())
    )


def backoff_for(attempt: int) -> timedelta:
    """Exponential backoff: 10s, 40s, 160s, ... capped at one hour."""
    return timedelta(seconds=min(3600, 10 * 4 ** max(0, attempt - 1)))


async def schedule_retry(
    session: AsyncSession, job: ClaimedJob, error: str, *, now: datetime | None = None
) -> bool:
    """Requeues a job after a transient error. Returns False when retries are exhausted.

    If a newer job for the same resource is already queued, this one is cancelled instead of
    requeued, because the newer job will do the same work with fresher input.
    Runs in the caller's transaction.
    """
    if job.is_last_attempt:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(status=DEAD, locked_at=None, last_error=error[:2000], updated_at=func.now())
        )
        return False

    now = now or _now()
    newer = aliased(Job)
    superseded = (
        select(newer.id)
        .where(
            newer.type == job.type,
            newer.resource_id == job.resource_id,
            newer.status == QUEUED,
        )
        .exists()
    )
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status=case((superseded, CANCELLED), else_=QUEUED),
            run_after=now + backoff_for(job.attempts),
            locked_at=None,
            last_error=error[:2000],
            updated_at=now,
        )
    )
    return True
