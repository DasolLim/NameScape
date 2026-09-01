from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Discovery, User
from app.modules.accounts import service as accounts_service
from app.modules.moderation import classifier
from tests.factories import build_place, build_user


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
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://test")


def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set("namescape_session", accounts_service._session_for(user).cookie)


async def settled_voter(session: AsyncSession, username: str) -> User:
    user = await build_user(session, username=username)
    user.created_at = datetime.now(UTC) - timedelta(days=5)
    place = await build_place(
        session, name=f"{username}'s find", geonames_id=hash(username) % 90_000 + 300_000
    )
    session.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await session.flush()
    return user


async def test_proposing_requires_an_account(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)

    response = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Unfortunate Bay"}
    )

    assert response.status_code == 401


async def test_a_proposal_opens_a_contest_and_the_board_shows_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    sign_in(client, await build_user(db, username="wit"))

    created = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Unfortunate Bay"}
    )
    board = await client.get(f"/api/contests/{place.id}")

    assert created.status_code == 201
    body = board.json()
    assert body["quorum"] == 15
    assert body["proposals"][0]["text"] == "The Unfortunate Bay"
    assert body["closes_at"] is not None


async def test_a_proposer_voting_for_themselves_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    author = await settled_voter(db, "wit")
    sign_in(client, author)
    created = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Unfortunate Bay"}
    )

    response = await client.post(
        "/api/votes", json={"proposal_id": created.json()["id"], "value": 1}
    )

    assert response.status_code == 403


async def test_a_settled_voter_can_agree(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    sign_in(client, author)
    created = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Unfortunate Bay"}
    )

    sign_in(client, await settled_voter(db, "voter"))
    response = await client.post(
        "/api/votes", json={"proposal_id": created.json()["id"], "value": 1}
    )

    assert response.status_code == 204
    board = (await client.get(f"/api/contests/{place.id}")).json()
    assert board["proposals"][0]["agree"] == 1


async def test_a_brand_new_account_cannot_vote(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)
    sign_in(client, await build_user(db, username="wit"))
    created = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Unfortunate Bay"}
    )

    sign_in(client, await build_user(db, username="brandnew"))
    response = await client.post(
        "/api/votes", json={"proposal_id": created.json()["id"], "value": 1}
    )

    assert response.status_code == 403
