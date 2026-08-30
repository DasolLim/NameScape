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


async def test_a_counter_left_without_a_ttl_heals_instead_of_locking_out(
    fake_redis: FakeRedis,
) -> None:
    """The failure that bit in development.

    INCR and EXPIRE used to be two awaits. A crash between them left a key
    with no TTL, and because the expiry was only set when the counter read 1,
    it never got one: that route stayed refused forever.
    """
    key = ratelimit.key_for(CLIENT_IP, "POST /api/discoveries")
    await fake_redis.set(key, 500)  # no TTL, well past the limit
    assert await fake_redis.ttl(key) == -1

    await ratelimit.count(fake_redis, key)

    assert await fake_redis.ttl(key) > 0


async def test_the_window_expires_so_the_allowance_returns(
    fake_redis: FakeRedis,
) -> None:
    key = ratelimit.key_for(CLIENT_IP, "POST /api/discoveries")

    await ratelimit.count(fake_redis, key)

    assert await fake_redis.ttl(key) == ratelimit.WINDOW_SECONDS


async def test_a_forged_forwarded_header_is_ignored_by_default(
    fake_redis: FakeRedis,
) -> None:
    """Trusting the header unconditionally would hand out a fresh allowance
    per request to anyone willing to set it."""
    assert settings.trust_forwarded_for is False

    assert ratelimit.address_of_client("10.0.0.1", forwarded_for="1.2.3.4") == "10.0.0.1"


async def test_a_client_behind_a_trusted_proxy_is_not_lumped_in_with_everyone(
    fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behind a load balancer every request shares the proxy's address, so
    without the forwarded header one busy visitor would refuse everyone."""
    monkeypatch.setattr(settings, "trust_forwarded_for", True)

    direct = ratelimit.address_of_client("10.0.0.1", forwarded_for=None)
    behind = ratelimit.address_of_client("10.0.0.1", forwarded_for="203.0.113.9, 10.0.0.1")
    other = ratelimit.address_of_client("10.0.0.1", forwarded_for="198.51.100.4")

    assert direct == "10.0.0.1"
    assert behind == "203.0.113.9"
    assert behind != other
