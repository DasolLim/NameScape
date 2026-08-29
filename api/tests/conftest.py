from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back when the test ends.

    The engine is per-test with NullPool: a shared engine would outlive the
    event loop pytest-asyncio gives each test and fail on teardown.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = async_sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    client = FakeRedis()
    try:
        yield client
    finally:
        await client.aclose()
