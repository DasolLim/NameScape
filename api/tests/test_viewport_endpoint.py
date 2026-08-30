import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Bookmark, Discovery
from app.modules.accounts import service as accounts_service
from tests.factories import build_place, build_user

BOUNDS = {"west": -54.0, "south": 47.0, "east": -53.0, "north": 48.0}


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


async def test_viewport_returns_pins_at_close_zoom(client: AsyncClient, db: AsyncSession) -> None:
    user = await build_user(db, username="finder")
    place = await build_place(db)
    db.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await db.flush()

    response = await client.get("/api/viewport", params={**BOUNDS, "zoom": 12})

    assert response.status_code == 200
    body = response.json()
    assert body["band"] == "pin"
    assert body["features"][0]["name"] == "Dildo"
    assert body["bookmarks"] == []


async def test_viewport_aggregates_by_country_at_planet_zoom(
    client: AsyncClient, db: AsyncSession
) -> None:
    user = await build_user(db, username="finder")
    place = await build_place(db)
    db.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await db.flush()

    body = (await client.get("/api/viewport", params={**BOUNDS, "zoom": 1})).json()

    assert body["band"] == "country"
    assert body["features"][0]["country_code"] == "CA"


async def test_bookmarks_come_back_only_for_a_signed_in_viewer(
    client: AsyncClient, db: AsyncSession
) -> None:
    viewer = await build_user(db, username="collector")
    place = await build_place(db)
    db.add(Bookmark(user_id=viewer.id, place_id=place.id))
    await db.flush()

    anonymous = (await client.get("/api/viewport", params={**BOUNDS, "zoom": 12})).json()
    client.cookies.set("toponomicon_session", accounts_service._session_for(viewer).cookie)
    signed_in = (await client.get("/api/viewport", params={**BOUNDS, "zoom": 12})).json()

    assert anonymous["bookmarks"] == []
    assert [b["name"] for b in signed_in["bookmarks"]] == ["Dildo"]
