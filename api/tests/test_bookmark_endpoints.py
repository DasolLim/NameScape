import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import User
from app.modules.accounts import service as accounts_service
from tests.factories import build_place, build_user


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)


async def test_bookmarking_requires_an_account(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)

    assert (await client.post(f"/api/bookmarks/{place.id}")).status_code == 401


async def test_bookmarking_twice_is_idempotent(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    sign_in(client, await build_user(db, username="collector"))

    first = await client.post(f"/api/bookmarks/{place.id}")
    second = await client.post(f"/api/bookmarks/{place.id}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert len((await client.get("/api/bookmarks")).json()["bookmarks"]) == 1


async def test_removing_twice_is_idempotent(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    sign_in(client, await build_user(db, username="collector"))
    await client.post(f"/api/bookmarks/{place.id}")

    first = await client.delete(f"/api/bookmarks/{place.id}")
    second = await client.delete(f"/api/bookmarks/{place.id}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert (await client.get("/api/bookmarks")).json()["bookmarks"] == []


async def test_the_list_joins_place_data(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    sign_in(client, await build_user(db, username="collector"))
    await client.post(f"/api/bookmarks/{place.id}")

    saved = (await client.get("/api/bookmarks")).json()["bookmarks"][0]

    assert saved["name"] == "Dildo"
    assert saved["country_code"] == "CA"
    assert saved["place_id"] == place.id
