import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.modules.accounts import delivery
from tests.factories import build_user


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    outbox: list[tuple[str, str]] = []

    async def capture(email: str, token: str) -> None:
        outbox.append((email, token))

    monkeypatch.setattr(delivery, "send_magic_link", capture)
    return outbox


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def test_signing_in_sets_a_hardened_cookie(
    client: AsyncClient, sent: list[tuple[str, str]]
) -> None:
    await client.post("/api/auth/magic-link", json={"email": "finder@example.com"})
    _, token = sent[0]

    response = await client.post("/api/auth/session", json={"token": token})

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie


async def test_a_bad_token_is_rejected_without_a_cookie(client: AsyncClient) -> None:
    response = await client.post("/api/auth/session", json={"token": "not-a-token"})

    assert response.status_code == 401
    assert "set-cookie" not in response.headers


async def test_me_reports_the_signed_in_user(
    client: AsyncClient, sent: list[tuple[str, str]]
) -> None:
    await client.post("/api/auth/magic-link", json={"email": "finder@example.com"})
    await client.post("/api/auth/session", json={"token": sent[0][1]})

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["username"].startswith("finder")


async def test_me_is_anonymous_without_a_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() is None


async def test_profile_and_passport_are_readable_without_an_account(
    client: AsyncClient, db: AsyncSession
) -> None:
    await build_user(db, username="publicfigure")

    profile = await client.get("/api/users/publicfigure")
    passport = await client.get("/api/passport/publicfigure")

    assert profile.status_code == 200
    assert profile.json()["username"] == "publicfigure"
    assert passport.json()["discoveries"] == 0


async def test_an_unknown_username_is_a_404_not_a_500(client: AsyncClient) -> None:
    assert (await client.get("/api/users/nobody")).status_code == 404


async def test_too_many_magic_links_is_rate_limited(
    client: AsyncClient, sent: list[tuple[str, str]]
) -> None:
    for _ in range(3):
        await client.post("/api/auth/magic-link", json={"email": "eager@example.com"})

    response = await client.post("/api/auth/magic-link", json={"email": "eager@example.com"})

    assert response.status_code == 429
