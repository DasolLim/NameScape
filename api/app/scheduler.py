"""Scheduled work: contest resolution, and releasing expired guest claims.

The worker must run as a single instance; the Redis lock is a second guard, so
a mistaken second process cannot resolve the same contest twice, or hand one
released place to two different people.
"""

import logging
from typing import Final

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from app.cache import get_redis
from app.db import SessionLocal
from app.modules import contests
from app.modules.discoveries import expiry

logger = logging.getLogger(__name__)

LOCK_KEY: Final = "lock:resolve-due"
#: Longer than a run can take, short enough that a crashed worker recovers.
LOCK_TTL_SECONDS: Final = 120
INTERVAL_SECONDS: Final = 60

RELEASE_LOCK_KEY: Final = "lock:release-expired"
#: Daily, per Addendum A. A guest claim is a week long, so a place sitting
#: held for a few hours past its deadline costs nothing.
RELEASE_INTERVAL_SECONDS: Final = 60 * 60 * 24


async def resolve_due_once(redis: Redis) -> int:
    """Resolve everything due, or do nothing if another worker holds the lock."""
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("resolve_due skipped: lock held elsewhere")
        return 0

    try:
        async with SessionLocal() as session:
            outcomes = await contests.resolve_due(session)
            await session.commit()
    finally:
        await redis.delete(LOCK_KEY)

    if outcomes:
        logger.info("resolved %d contests", len(outcomes))
    return len(outcomes)


async def release_expired_once(redis: Redis) -> int:
    """Release every claim past its deadline, unless another worker is on it."""
    acquired = await redis.set(RELEASE_LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.info("release_expired skipped: lock held elsewhere")
        return 0

    try:
        async with SessionLocal() as session:
            released = await expiry.release_expired(session)
            await session.commit()
    finally:
        await redis.delete(RELEASE_LOCK_KEY)

    if released:
        logger.info("released %d expired guest claims", released)
    return released


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
    return scheduler


async def _tick() -> None:
    async for redis in get_redis():
        await resolve_due_once(redis)
        break


async def _release_tick() -> None:
    async for redis in get_redis():
        await release_expired_once(redis)
        break
