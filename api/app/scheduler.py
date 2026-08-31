"""Scheduled work: contest resolution, guest claim expiry, puzzle rollover.

The worker must run as a single instance; the Redis lock is a second guard, so
a mistaken second process cannot resolve the same contest twice, or hand one
released place to two different people.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.config import settings
from app.db import SessionLocal
from app.modules import contests
from app.modules.discoveries import expiry
from app.modules.puzzles import rollover

logger = logging.getLogger(__name__)

LOCK_KEY: Final = "lock:resolve-due"
#: Longer than a run can take, short enough that a crashed worker recovers.
LOCK_TTL_SECONDS: Final = 120
INTERVAL_SECONDS: Final = 60

ROLLOVER_LOCK_KEY: Final = "lock:puzzle-rollover"
#: Hourly, not daily. The handover is keyed to a UTC date, so a worker that
#: checks once a day and happens to check at 23:50 would leave today's puzzle
#: unplayable for the ten minutes that matter, and yesterday's live for a day.
ROLLOVER_INTERVAL_SECONDS: Final = 60 * 60

RELEASE_LOCK_KEY: Final = "lock:release-expired"
#: Daily, per Addendum A. A guest claim is a week long, so a place sitting
#: held for a few hours past its deadline costs nothing.
RELEASE_INTERVAL_SECONDS: Final = 60 * 60 * 24


@asynccontextmanager
async def _session(borrowed: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """Use the caller's session, or open one.

    A timer has no request to borrow from, so it opens its own. Invoked over
    HTTP there is a request session already, and using it is what keeps the
    endpoint honest: otherwise the job reaches past its caller straight to the
    global engine, which in a test means straight to the real database.
    """
    if borrowed is not None:
        yield borrowed
        return
    async with SessionLocal() as owned:
        yield owned


def should_run() -> bool:
    """Whether this process runs the jobs itself.

    Off on serverless, where every function instance would start its own
    scheduler and the Redis lock would be doing all the work. There, cron
    invokes the same functions over HTTP instead.
    """
    return settings.run_scheduler


async def resolve_due_once(redis: Redis, session: AsyncSession | None = None) -> int:
    """Resolve everything due, or do nothing if another worker holds the lock."""
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("resolve_due skipped: lock held elsewhere")
        return 0

    try:
        async with _session(session) as active:
            outcomes = await contests.resolve_due(active)
            await active.commit()
    finally:
        await redis.delete(LOCK_KEY)

    if outcomes:
        logger.info("resolved %d contests", len(outcomes))
    return len(outcomes)


async def release_expired_once(redis: Redis, session: AsyncSession | None = None) -> int:
    """Release every claim past its deadline, unless another worker is on it."""
    acquired = await redis.set(RELEASE_LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("release_expired skipped: lock held elsewhere")
        return 0

    try:
        async with _session(session) as active:
            released = await expiry.release_expired(active)
            await active.commit()
    finally:
        await redis.delete(RELEASE_LOCK_KEY)

    if released:
        logger.info("released %d expired guest claims", released)
    return released


async def roll_over_once(redis: Redis, session: AsyncSession | None = None) -> int:
    """Hand the day over, unless another worker is already doing it."""
    acquired = await redis.set(ROLLOVER_LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("puzzle rollover skipped: lock held elsewhere")
        return 0

    try:
        async with _session(session) as active:
            changed = await rollover.roll_over(active)
            await active.commit()
    finally:
        await redis.delete(ROLLOVER_LOCK_KEY)

    return changed


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _tick,
        "interval",
        seconds=INTERVAL_SECONDS,
        id="resolve-due",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _release_tick,
        "interval",
        seconds=RELEASE_INTERVAL_SECONDS,
        id="release-expired",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _rollover_tick,
        "interval",
        seconds=ROLLOVER_INTERVAL_SECONDS,
        id="puzzle-rollover",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def _tick() -> None:
    async for redis in get_redis():
        await resolve_due_once(redis)
        break


async def _release_tick() -> None:
    async for redis in get_redis():
        await release_expired_once(redis)
        break


async def _rollover_tick() -> None:
    async for redis in get_redis():
        await roll_over_once(redis)
        break
