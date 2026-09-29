"""Fixed-window counters stored in Postgres.

Keeping counters in the database makes limits hold across API processes and restarts
without introducing Redis.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, Integer, String, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from knowvault.core.db import Base

# Windows older than this are deleted opportunistically on each increment.
_RETENTION = timedelta(days=1)


class UsageCounter(Base):
    __tablename__ = "usage_counters"

    subject: Mapped[str] = mapped_column(String(320), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def window_start_for(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


def seconds_until_reset(now: datetime, window: timedelta) -> int:
    reset_at = window_start_for(now, window) + window
    return max(1, int((reset_at - now).total_seconds()))


async def current_count(
    session: AsyncSession,
    *,
    subject: str,
    bucket: str,
    window: timedelta,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    count = await session.scalar(
        select(UsageCounter.count).where(
            UsageCounter.subject == subject,
            UsageCounter.bucket == bucket,
            UsageCounter.window_start == window_start_for(now, window),
        )
    )
    return count or 0


async def increment(
    session: AsyncSession,
    *,
    subject: str,
    bucket: str,
    window: timedelta,
    now: datetime | None = None,
) -> int:
    """Atomically increments the counter for the current window and returns the new value."""
    now = now or datetime.now(UTC)
    statement = (
        insert(UsageCounter)
        .values(subject=subject, bucket=bucket, window_start=window_start_for(now, window), count=1)
        .on_conflict_do_update(
            index_elements=[UsageCounter.subject, UsageCounter.bucket, UsageCounter.window_start],
            set_={"count": UsageCounter.count + 1},
        )
        .returning(UsageCounter.count)
    )
    new_count = (await session.execute(statement)).scalar_one()
    await session.execute(delete(UsageCounter).where(UsageCounter.window_start < now - _RETENTION))
    return new_count
