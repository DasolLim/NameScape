"""Per-address rate limiting for write endpoints.

The address is hashed before it is used, and only the hash is stored, in
Redis, with a TTL. No IP address ever reaches Postgres.
"""

import hashlib
import hmac
from typing import Final

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings

WINDOW_SECONDS: Final = 60

#: Only these methods are limited; reading is never gated.
LIMITED_METHODS: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def key_for(address: str, route: str) -> str:
    """A stable, non-reversible key. The secret stops it being a rainbow table."""
    digest = hmac.new(
        settings.secret_key.encode(), f"{address}|{route}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"ratelimit:{digest}"


def _route_of(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    return f"{request.method} {path}"


async def enforce(request: Request, redis: Redis) -> None:
    """Raise 429 once an address has spent its allowance for this route."""
    if request.method not in LIMITED_METHODS:
        return

    address = request.client.host if request.client else "unknown"
    key = key_for(address, _route_of(request))

    try:
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, WINDOW_SECONDS)
    except (RedisError, OSError) as unreachable:
        # Without Redis there is no limit at all, so writes stop rather than
        # run unbounded. Reads are untouched.
        raise HTTPException(
            status_code=503, detail="Writes are temporarily unavailable"
        ) from unreachable
    if used > settings.writes_per_minute:
        # Deliberately vague: the limit is not a hint to work around.
        raise HTTPException(status_code=429, detail="Too many requests")
