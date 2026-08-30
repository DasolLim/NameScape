"""What survives when a dependency dies. PRD step 22's checklist."""

from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Discovery
from app.modules import gazetteer, viewport
from app.modules.gazetteer import backends
from app.modules.gazetteer.importer import import_geonames
from app.modules.viewport import service as viewport_service
from tests.factories import build_place, build_user

FIXTURE = Path(__file__).parent / "fixtures" / "geonames_sample.txt"
BOUNDS = viewport_service.BBox(-54.0, 47.0, -53.0, 48.0)


class DeadPipeline:
    """Queues without complaint, then fails on execute, as a real one does."""

    def incr(self, *_args: object, **_kwargs: object) -> "DeadPipeline":
        return self

    def expire(self, *_args: object, **_kwargs: object) -> "DeadPipeline":
        return self

    async def execute(self) -> list[object]:
        raise RedisConnectionError("redis is down")


class DeadRedis:
    """Every call fails, the way an unreachable Redis does."""

    async def get(self, *_args: object, **_kwargs: object) -> bytes:
        raise RedisConnectionError("redis is down")

    async def set(self, *_args: object, **_kwargs: object) -> bool:
        raise RedisConnectionError("redis is down")

    async def incr(self, *_args: object, **_kwargs: object) -> int:
        raise RedisConnectionError("redis is down")

    async def expire(self, *_args: object, **_kwargs: object) -> bool:
        raise RedisConnectionError("redis is down")

    def pipeline(self, *_args: object, **_kwargs: object) -> DeadPipeline:
        return DeadPipeline()


async def test_typesense_down_falls_back_to_trigram_search(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await import_geonames(db, FIXTURE)

    async def unavailable(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(backends, "typesense_ids", unavailable)

    results = await gazetteer.search(db, "Dildo")

    assert [r.name for r in results] == ["Dildo"]


async def test_photon_down_leaves_exact_search_working(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await import_geonames(db, FIXTURE)

    async def unavailable(*_a: object, **_k: object) -> None:
        return None

    async def photon_is_dead(*_a: object, **_k: object) -> list[int]:
        raise ConnectionError("photon is down")

    monkeypatch.setattr(backends, "typesense_ids", unavailable)
    monkeypatch.setattr(backends, "photon_ids", photon_is_dead)

    # An exact match never reaches the fuzzy backend.
    assert [r.name for r in await gazetteer.search(db, "Dildo")] == ["Dildo"]


async def test_redis_down_still_serves_the_viewport_from_postgres(
    db: AsyncSession,
) -> None:
    user = await build_user(db, username="finder")
    place = await build_place(db)
    db.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await db.flush()

    data = await viewport.query(db, DeadRedis(), BOUNDS, zoom=12)  # type: ignore[arg-type]

    assert [feature.name for feature in data.features] == ["Dildo"]


async def test_redis_down_disables_writes_rather_than_letting_them_through(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    """Without Redis there is no rate limit, so writes fail closed."""
    place = await build_place(db)
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.state.redis = DeadRedis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post(f"/api/bookmarks/{place.id}")

    assert response.status_code == 503
