import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability
from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.modules import viewport
from app.modules.viewport import service as viewport_service
from tests.factories import build_place


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.state.redis = fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.headers["x-request-id"]


async def test_a_supplied_request_id_is_propagated_not_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["x-request-id"] == "abc-123"


async def test_metrics_expose_the_numbers_the_runbook_needs(client: AsyncClient) -> None:
    body = (await client.get("/metrics")).text

    for metric in (
        "namescape_search_seconds",
        "namescape_viewport_cache_total",
        "namescape_contests_resolved_total",
        "namescape_moderation_rejected_total",
    ):
        assert metric in body


async def test_the_viewport_cache_records_hits_and_misses(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    await build_place(db)
    bbox = viewport_service.BBox(-54.0, 47.0, -53.0, 48.0)
    before_miss = observability.cache_events("miss")
    before_hit = observability.cache_events("hit")

    await viewport.query(db, fake_redis, bbox, zoom=12)
    await viewport.query(db, fake_redis, bbox, zoom=12)

    assert observability.cache_events("miss") == before_miss + 1
    assert observability.cache_events("hit") == before_hit + 1
