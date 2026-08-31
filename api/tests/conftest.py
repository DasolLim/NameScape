import asyncio
import os
import subprocess
from collections.abc import AsyncIterator, Iterator

import asyncpg
import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

TEST_DATABASE_SUFFIX = "_test"


def _test_database_url() -> str:
    base, _, name = settings.database_url.rpartition("/")
    return f"{base}/{name}{TEST_DATABASE_SUFFIX}"


async def _create_database_if_missing(url: str) -> None:
    base, _, name = url.rpartition("/")
    dsn = f"{base}/postgres".replace("postgresql+asyncpg://", "postgresql://")

    connection = await asyncpg.connect(dsn)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{name}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[str]:
    """A database of its own, so `make seed` data can never reach a test."""
    url = _test_database_url()
    asyncio.run(_create_database_if_missing(url))

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
    )
    yield url


@pytest.fixture
async def db(test_database: str) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back when the test ends.

    The engine is per-test with NullPool: a shared engine would outlive the
    event loop pytest-asyncio gives each test and fail on teardown.
    """
    engine = create_async_engine(test_database, poolclass=NullPool)
    connection = await engine.connect()
    transaction = await connection.begin()
    # create_savepoint keeps a route handler's session.commit() inside this
    # transaction, so committing endpoints cannot escape the rollback.
    session = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()
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


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a real service, and cannot do so by omission.

    Two holes this closes. A test that called gazetteer.enrich() without
    mocking its sources was quietly making live Wikidata and Wikipedia
    requests, and passing only because they happened to return nothing useful.
    Then, the moment an OPENROUTER_API_KEY existed in .env, the same test
    started spending money and asserting against whatever a model said.

    The rule: inside a test, an httpx client with no explicit transport is a
    real network call. Endpoint tests pass ASGITransport and are unaffected.
    """
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    real_client = httpx.AsyncClient

    class Guarded(real_client):  # type: ignore[misc,valid-type]
        def __init__(self, *args: object, **kwargs: object) -> None:
            if kwargs.get("transport") is None:
                raise RuntimeError(
                    "a test tried to open a real network connection. Mock the "
                    "backend it calls, or pass an explicit httpx transport."
                )
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Guarded)


@pytest.fixture(autouse=True)
async def isolated_app_state(fake_redis: FakeRedis) -> AsyncIterator[None]:
    """No test may reach the development Redis.

    The rate-limit middleware reads app.state.redis directly, because
    middleware cannot use FastAPI dependencies. Dependency overrides are also
    cleared so one endpoint test cannot leak a session into the next.
    """
    from app.main import app

    original = getattr(app.state, "redis", None)
    app.state.redis = fake_redis
    try:
        yield
    finally:
        app.state.redis = original
        app.dependency_overrides.clear()
