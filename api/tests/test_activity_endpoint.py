from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Contest, Discovery, User
from app.modules.accounts import service as accounts_service
from tests.factories import build_place, build_user


@pytest.fixture
async def client(db: AsyncSession, fake_redis: FakeRedis) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)


async def test_an_anonymous_visitor_gets_contest_activity_but_no_streak(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    db.add(
        Contest(
            place_id=place.id,
            status="open",
            opened_at=datetime.now(UTC),
            closes_at=datetime.now(UTC) + timedelta(hours=3),
        )
    )
    await db.flush()

    body = (await client.get("/api/activity")).json()

    assert body["contests_closing_soon"] == 1
    assert body["streak_days"] is None


async def test_a_signed_in_visitor_gets_their_streak(client: AsyncClient, db: AsyncSession) -> None:
    user = await build_user(db, username="collector")
    sign_in(client, user)
    for offset in (0, 1, 2):
        place = await build_place(db, name=f"Find {offset}", geonames_id=810_000 + offset)
        db.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
        await db.flush()
        await db.execute(
            text("UPDATE discoveries SET created_at = :when WHERE place_id = :place"),
            {"when": datetime.now(UTC) - timedelta(days=offset), "place": place.id},
        )

    body = (await client.get("/api/activity")).json()

    assert body["streak_days"] == 3
    assert body["streak_at_risk"] is False


async def test_a_contest_closing_next_week_is_not_closing_soon(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    db.add(
        Contest(
            place_id=place.id,
            status="open",
            opened_at=datetime.now(UTC),
            closes_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    await db.flush()

    assert (await client.get("/api/activity")).json()["contests_closing_soon"] == 0


async def test_a_resolved_contest_is_not_counted(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    db.add(
        Contest(
            place_id=place.id,
            status="resolved",
            opened_at=datetime.now(UTC),
            closes_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.flush()

    assert (await client.get("/api/activity")).json()["contests_closing_soon"] == 0
