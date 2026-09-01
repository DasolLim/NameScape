"""What has to be true for this to run somewhere other than a laptop.

Three separate concerns, all of which were broken or absent:

The scheduler was never started by anything but a test, so contests never
resolved, guest claims never expired and puzzles never went live.

A pooled Postgres connection cannot use prepared statements, and asyncpg caches
them by default. On Supabase's transaction pooler that is not a slow path, it is
an error on the second query.

Serverless has no long-running process, so the scheduled work has to be
reachable over HTTP, and that endpoint must not be open to the world.
"""

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import db, scheduler
from app.cache import get_redis
from app.config import settings
from app.db import get_session
from app.main import app


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


# --- The scheduler -----------------------------------------------------------


def test_the_scheduler_owns_every_job_that_needs_a_timer() -> None:
    """If a job is not here, nothing runs it: these three were dead code."""
    built = scheduler.build_scheduler()

    assert {job.id for job in built.get_jobs()} == {
        "resolve-due",
        "release-expired",
        "puzzle-rollover",
    }


def test_a_long_running_process_starts_the_scheduler_when_told_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "run_scheduler", True)

    assert scheduler.should_run() is True


def test_serverless_does_not_start_a_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every function instance would start its own, and a Redis lock is a second
    guard rather than a licence to run many. Off unless a process opts in."""
    monkeypatch.setattr(settings, "run_scheduler", False)

    assert scheduler.should_run() is False


def test_it_is_off_by_default_so_serverless_is_safe_without_configuring_anything() -> None:
    assert settings.run_scheduler is False


# --- Pooled Postgres ---------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "pooled"),
    [
        ("postgresql+asyncpg://u:p@aws-0-us-west-2.pooler.supabase.com:6543/postgres", True),
        ("postgresql+asyncpg://u:p@aws-0-us-west-2.pooler.supabase.com:5432/postgres", False),
        ("postgresql+asyncpg://u:p@db.abc.supabase.co:5432/postgres", False),
        ("postgresql+asyncpg://u:p@localhost:55432/namescape", False),
    ],
)
def test_only_the_transaction_pooler_is_treated_as_pooled(url: str, pooled: bool) -> None:
    """Port 6543 is Supavisor's transaction mode, the one without prepared
    statements. Session mode on 5432 has them, and so does a direct connection."""
    assert db.is_pooled(url) is pooled


def test_a_pooled_connection_disables_the_prepared_statement_cache() -> None:
    """asyncpg caches prepared statements by default. Through a transaction
    pooler that is an error on the second query, not a slow path."""
    args = db.connect_args_for(
        "postgresql+asyncpg://u:p@aws-0-us-west-2.pooler.supabase.com:6543/postgres"
    )

    assert args["prepared_statement_cache_size"] == 0
    assert args["statement_cache_size"] == 0


def test_a_direct_connection_keeps_its_cache() -> None:
    assert db.connect_args_for("postgresql+asyncpg://u:p@localhost:55432/namescape") == {}


def test_migrations_target_a_connection_that_has_prepared_statements() -> None:
    """Alembic through the transaction pooler fails partway. The direct URL
    falls back to the runtime one so local development needs no extra setting."""
    assert settings.database_url_direct is not None


# --- Cron over HTTP ---------------------------------------------------------


async def test_a_cron_endpoint_refuses_a_caller_without_the_secret(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These endpoints resolve contests and release claims. Open to the world
    they would be a way to force either at will."""
    monkeypatch.setattr(settings, "cron_secret", "expected")

    response = await client.post("/api/cron/resolve-due")

    assert response.status_code == 401


async def test_a_cron_endpoint_refuses_the_wrong_secret(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cron_secret", "expected")

    response = await client.post("/api/cron/resolve-due", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401


async def test_an_unconfigured_secret_refuses_everything(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed. An unset secret must not mean an open endpoint."""
    monkeypatch.setattr(settings, "cron_secret", "")

    response = await client.post(
        "/api/cron/resolve-due", headers={"Authorization": "Bearer anything"}
    )

    assert response.status_code == 401


@pytest.mark.parametrize("job", ["resolve-due", "release-expired", "puzzle-rollover"])
async def test_each_scheduled_job_is_reachable_with_the_secret(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, job: str
) -> None:
    monkeypatch.setattr(settings, "cron_secret", "expected")

    response = await client.post(f"/api/cron/{job}", headers={"Authorization": "Bearer expected"})

    assert response.status_code == 200
    assert "changed" in response.json()


@pytest.mark.parametrize("job", ["resolve-due", "release-expired", "puzzle-rollover"])
async def test_a_scheduler_that_can_only_send_get_is_still_able_to_run_a_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, job: str
) -> None:
    """Vercel cron invokes with GET, not POST, and does not follow redirects.
    A POST-only endpoint would have deployed cleanly and never run once."""
    monkeypatch.setattr(settings, "cron_secret", "expected")

    response = await client.get(f"/api/cron/{job}", headers={"Authorization": "Bearer expected"})

    assert response.status_code == 200
    assert "changed" in response.json()


async def test_a_get_without_the_secret_is_still_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cron_secret", "expected")

    assert (await client.get("/api/cron/resolve-due")).status_code == 401


async def test_a_cron_run_uses_the_callers_session_not_the_global_engine(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It reached past its caller to the global engine before, which in a test
    meant reaching the real database. Proven by doing real work through the
    injected session and seeing the result there."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func, select

    from app.models import Discovery
    from tests.factories import build_guest_session, build_place

    monkeypatch.setattr(settings, "cron_secret", "expected")
    place = await build_place(db)
    guest = await build_guest_session(db)
    db.add(
        Discovery(
            place_id=place.id,
            claimant_type="guest",
            guest_session_id=guest.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
            caption="found it",
        )
    )
    await db.flush()

    response = await client.post(
        "/api/cron/release-expired", headers={"Authorization": "Bearer expected"}
    )

    assert response.json() == {"job": "release-expired", "changed": 1}
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 0


async def test_an_unknown_job_is_a_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "cron_secret", "expected")

    response = await client.post(
        "/api/cron/do-something-else", headers={"Authorization": "Bearer expected"}
    )

    assert response.status_code == 404
