from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis

from app import scheduler
from app.modules import contests
from app.modules.discoveries import expiry
from app.modules.puzzles import rollover


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

    async def release_expired(_session: Any) -> int:
        calls.append("release")
        return 0

    monkeypatch.setattr(scheduler, "SessionLocal", session_factory)
    monkeypatch.setattr(contests, "resolve_due", resolve_due)

    async def roll(_session: Any) -> int:
        calls.append("roll")
        return 0

    monkeypatch.setattr(expiry, "release_expired", release_expired)
    monkeypatch.setattr(rollover, "roll_over", roll)
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


async def test_the_lock_stops_a_second_worker_from_releasing_claims(
    fake_redis: FakeRedis, no_database: list[str]
) -> None:
    """Releasing twice would hand one place to two people."""
    await fake_redis.set(scheduler.RELEASE_LOCK_KEY, "1", ex=60)

    assert await scheduler.release_expired_once(fake_redis) == 0
    assert no_database == []


async def test_a_release_run_deletes_and_then_frees_the_lock(
    fake_redis: FakeRedis, no_database: list[str]
) -> None:
    await scheduler.release_expired_once(fake_redis)

    assert no_database == ["release", "commit"]
    assert await fake_redis.get(scheduler.RELEASE_LOCK_KEY) is None


async def test_the_lock_stops_a_second_worker_rolling_the_puzzle_over(
    fake_redis: FakeRedis, no_database: list[str]
) -> None:
    await fake_redis.set(scheduler.ROLLOVER_LOCK_KEY, "1", ex=60)

    assert await scheduler.roll_over_once(fake_redis) == 0
    assert no_database == []


async def test_a_rollover_run_frees_the_lock(fake_redis: FakeRedis, no_database: list[str]) -> None:
    await scheduler.roll_over_once(fake_redis)

    assert no_database == ["roll", "commit"]
    assert await fake_redis.get(scheduler.ROLLOVER_LOCK_KEY) is None


@pytest.mark.parametrize("job_id", ["resolve-due", "release-expired", "puzzle-rollover"])
def test_every_job_runs_one_instance_at_a_time(job_id: str) -> None:
    job = scheduler.build_scheduler().get_job(job_id)

    assert job is not None
    assert job.max_instances == 1
    assert job.coalesce is True
