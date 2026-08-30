"""Contest resolution on a timer.

The worker must run as a single instance; the Redis lock is a second guard, so
a mistaken second process cannot resolve the same contest twice.
"""

import logging
from typing import Final

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from app.cache import get_redis
from app.db import SessionLocal
from app.modules import contests

logger = logging.getLogger(__name__)

LOCK_KEY: Final = "lock:resolve-due"
#: Longer than a run can take, short enough that a crashed worker recovers.
LOCK_TTL_SECONDS: Final = 120
INTERVAL_SECONDS: Final = 60


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
    return scheduler


async def _tick() -> None:
    async for redis in get_redis():
        await resolve_due_once(redis)
        break
