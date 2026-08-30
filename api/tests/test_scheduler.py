from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis

from app import scheduler
from app.modules import contests


@pytest.fixture(autouse=True)
def no_database(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """This is a test about the lock, not about resolution or the database."""
    calls: list[str] = []

    class FakeSession:
        async def commit(self) -> None:
            calls.append("commit")

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[FakeSession]:
        yield FakeSession()

    async def resolve_due(_session: Any) -> list[str]:
        calls.append("resolve")
        return []

    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(contests, "resolve_due", resolve_due)
    return calls


async def test_the_lock_stops_a_second_worker_from_resolving(
    fake_redis: FakeRedis, no_database: list[str]
) -> None:
    """A double-resolved contest is the failure this lock exists to prevent."""
    await fake_redis.set(scheduler.LOCK_KEY, "1", ex=60)

    resolved = await scheduler.resolve_due_once(fake_redis)

    assert resolved == 0
    assert no_database == []
    assert await fake_redis.get(scheduler.LOCK_KEY) == b"1"


async def test_a_run_resolves_and_then_releases_the_lock(
    fake_redis: FakeRedis, no_database: list[str]
) -> None:
    await scheduler.resolve_due_once(fake_redis)

    assert no_database == ["resolve", "commit"]
    assert await fake_redis.get(scheduler.LOCK_KEY) is None


def test_the_job_runs_one_instance_at_a_time() -> None:
    job = scheduler.build_scheduler().get_job("resolve-due")

    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True
