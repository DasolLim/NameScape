"""Clear guest claims and the guest allowance, for end-to-end tests.

Development only. The allowance is three claims per hashed address per day,
which is right in production and impossible to test against more than three
times a day, so a browser test needs a way to start from nothing.

The keys are HMACs of an address, so they cannot be reversed to find just the
guest ones. This deletes the local rate-limit keyspace wholesale, which is why
it must never point at anything but a development Redis.
"""

import asyncio

from sqlalchemy import text

from app.cache import build_client
from app.db import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        # The discoveries go with the sessions: ON DELETE CASCADE.
        released = await session.execute(text("DELETE FROM guest_sessions RETURNING id"))
        await session.commit()
        print(f"cleared {len(released.scalars().all())} guest sessions")

    redis = build_client()
    keys = [key async for key in redis.scan_iter("ratelimit:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()
    print(f"cleared {len(keys)} rate-limit keys")


if __name__ == "__main__":
    asyncio.run(main())
