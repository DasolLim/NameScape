from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.config import settings


async def get_redis() -> AsyncIterator[Redis]:
    """FastAPI dependency: one Redis client per request."""
    client: Redis = Redis.from_url(settings.redis_url)
    try:
        yield client
    finally:
        await client.aclose()
