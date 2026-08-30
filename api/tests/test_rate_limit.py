import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import ratelimit
from app.cache import get_redis
from app.config import settings
from app.db import get_session
from app.main import app
from app.modules.moderation import classifier
from tests.factories import build_place, build_user

CLIENT_IP = "203.0.113.9"


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    # Middleware reads app.state, not the dependency graph.
    app.state.redis = fake_redis
    return AsyncClient(
        transport=ASGITransport(app=app, client=(CLIENT_IP, 1234)),
        base_url="https://test",
    )


def test_the_key_hashes_the_address_and_never_contains_it() -> None:
    key = ratelimit.key_for(CLIENT_IP, "POST /api/discoveries")

    assert CLIENT_IP not in key
    assert key.startswith("ratelimit:")
    # Same address, same key; different address, different key.
    assert key == ratelimit.key_for(CLIENT_IP, "POST /api/discoveries")
    assert key != ratelimit.key_for("198.51.100.4", "POST /api/discoveries")


def test_limits_are_per_route() -> None:
    assert ratelimit.key_for(CLIENT_IP, "POST /api/votes") != ratelimit.key_for(
        CLIENT_IP, "POST /api/proposals"
    )


async def test_a_flood_of_writes_is_refused_with_429(
    client: AsyncClient, db: AsyncSession, fake_redis: FakeRedis
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="flooder")
    from app.modules.accounts import service as accounts_service

    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)

    statuses = []
    for index in range(settings.writes_per_minute + 3):
        response = await client.post(
            "/api/bookmarks/" + str(place.id) if index % 2 else f"/api/bookmarks/{place.id}"
        )
        statuses.append(response.status_code)

    assert 429 in statuses
    assert statuses.count(429) == 3


async def test_reads_are_not_rate_limited(client: AsyncClient, db: AsyncSession) -> None:
    await build_place(db)

    statuses = [
        (await client.get("/api/search", params={"q": "Dildo"})).status_code
        for _ in range(settings.writes_per_minute + 5)
    ]

    assert 429 not in statuses


async def test_no_raw_address_reaches_redis(
    client: AsyncClient, db: AsyncSession, fake_redis: FakeRedis
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="one")
    from app.modules.accounts import service as accounts_service

    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)
    await client.post(f"/api/bookmarks/{place.id}")

    keys = [
        key.decode() if isinstance(key, bytes) else str(key) for key in await fake_redis.keys("*")
    ]

    assert any(key.startswith("ratelimit:") for key in keys)
    assert all(CLIENT_IP not in key for key in keys)
