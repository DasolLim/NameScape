from fakeredis.aioredis import FakeRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from tests.factories import build_user


async def test_harness_provides_a_database_a_cache_and_builders(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    user = await build_user(db, username="dildo_hunter")

    assert user.id is not None
    assert user.username == "dildo_hunter"

    await fake_redis.set("spin", "4deg")
    assert await fake_redis.get("spin") == b"4deg"


async def test_each_test_starts_from_a_clean_database(db: AsyncSession) -> None:
    """Proves the transactional fixture rolls back what the previous test wrote."""
    usernames = (await db.execute(select(User.username))).scalars().all()

    assert "dildo_hunter" not in usernames
