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


def address_of_client(peer: str, forwarded_for: str | None) -> str:
    """Who to count against.

    Behind a load balancer every request arrives from the proxy, so counting
    the peer would put every visitor in one bucket and let a single busy one
    refuse everybody. The left-most forwarded address is the original client.
    """
    if settings.trust_forwarded_for and forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return peer


async def count(redis: Redis, key: str) -> int:
    """Increment the window and guarantee it expires.

    The increment and the expiry go in one pipeline. As two separate calls a
    crash in between left a key with no TTL, and since the expiry was only set
    when the counter read 1, it never got one - that route stayed refused
    forever. `nx=True` also heals any key already in that state.
    """
    pipeline = redis.pipeline()
    pipeline.incr(key)
    pipeline.expire(key, WINDOW_SECONDS, nx=True)
    used, _ = await pipeline.execute()
    return int(used)


def _route_of(request: Request) -> str:
    # Middleware runs before routing, so scope["route"] is usually absent and
    # the raw path is what identifies the endpoint.
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    return f"{request.method} {path}"


async def enforce(request: Request, redis: Redis) -> None:
    """Raise 429 once an address has spent its allowance for this route."""
    if request.method not in LIMITED_METHODS:
        return

    peer = request.client.host if request.client else "unknown"
    address = address_of_client(peer, request.headers.get("X-Forwarded-For"))

    try:
        used = await count(redis, key_for(address, _route_of(request)))
    except (RedisError, OSError) as unreachable:
        # Without Redis there is no limit at all, so writes stop rather than
        # run unbounded. Reads are untouched.
        raise HTTPException(
            status_code=503, detail="Writes are temporarily unavailable"
        ) from unreachable

    if used > settings.writes_per_minute:
        # Deliberately vague: the limit is not a hint to work around.
        raise HTTPException(status_code=429, detail="Too many requests")
