"""What an unsigned visitor may and may not do over HTTP.

Claiming is the one write a guest gets. Voting, bookmarking and proposing all
need an account, and each has to say so rather than failing quietly.
"""

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import Discovery, GuestSession
from app.modules.moderation import classifier
from tests.factories import build_place

CAPTION = "A real place, and the name is real too."
GUEST_COOKIE = "toponomicon_guest"


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


async def test_a_guest_can_claim_and_is_given_a_session_cookie(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    # Diffed rather than counted: the ids present before the request are none
    # of this test's business, and a leftover row should not fail it.
    before = set((await db.execute(select(GuestSession.id))).scalars().all())

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["place_id"] == place.id
    assert body["expires_at"] is not None
    assert GUEST_COOKIE in response.cookies

    after = set((await db.execute(select(GuestSession.id))).scalars().all())
    opened = after - before
    assert len(opened) == 1
    stored = (
        (await db.execute(select(Discovery).where(Discovery.place_id == place.id))).scalars().one()
    )
    assert stored.guest_session_id == opened.pop()


async def test_a_signed_in_claim_is_unchanged_and_has_no_deadline(
    client: AsyncClient, db: AsyncSession
) -> None:
    from app.modules.accounts import service as accounts_service
    from tests.factories import build_user

    place = await build_place(db)
    user = await build_user(db, username="finder")
    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 201
    assert response.json()["finder"] == "finder"
    assert response.json()["expires_at"] is None
    assert GUEST_COOKIE not in response.cookies


async def test_a_guest_keeps_one_claim_across_requests(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The cookie comes back, so the second attempt is refused, not doubled."""
    first = await build_place(db)
    second = await build_place(db, name="Boring", geonames_id=5_713_376)

    await client.post("/api/discoveries", json={"place_id": first.id, "caption": CAPTION})
    again = await client.post("/api/discoveries", json={"place_id": second.id, "caption": CAPTION})

    assert again.status_code == 403
    assert (await db.execute(select(Discovery))).scalars().all().__len__() == 1


async def test_a_fourth_guest_claim_from_one_address_is_refused(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    places = [await build_place(db, name=f"Place {n}", geonames_id=9_200_000 + n) for n in range(4)]

    codes = []
    for place in places:
        # A fresh client each time: one guest session gets one claim anyway, so
        # the only thing left holding the line is the hashed address.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as fresh:
            response = await fresh.post(
                "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
            )
            codes.append(response.status_code)

    assert codes == [201, 201, 201, 429]


async def test_no_ip_address_reaches_postgres(db: AsyncSession, fake_redis: FakeRedis) -> None:
    """The allowance lives in Redis, hashed. Postgres never learns the address."""
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    place = await build_place(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as fresh:
        await fresh.post("/api/discoveries", json={"place_id": place.id, "caption": CAPTION})

    keys = [
        key.decode() if isinstance(key, bytes) else str(key) for key in await fake_redis.keys("*")
    ]
    assert any(key.startswith("ratelimit:") for key in keys)
    assert not any("127.0.0.1" in key for key in keys)


async def test_signing_in_keeps_the_claim_and_clears_the_guest_cookie(
    client: AsyncClient, db: AsyncSession, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the deadline: signing up is how you keep the place."""
    from app.modules.accounts import delivery

    outbox: list[tuple[str, str]] = []

    async def capture(email: str, token: str) -> None:
        outbox.append((email, token))

    monkeypatch.setattr(delivery, "send_magic_link", capture)
    place = await build_place(db)

    claimed = await client.post("/api/discoveries", json={"place_id": place.id, "caption": CAPTION})
    assert claimed.status_code == 201
    assert client.cookies.get(GUEST_COOKIE) is not None

    await client.post("/api/auth/magic-link", json={"email": "keeper@example.com"})
    signed_in = await client.post("/api/auth/session", json={"token": outbox[0][1]})

    assert signed_in.status_code == 200
    mine = await client.get("/api/discoveries")
    assert [found["place_id"] for found in mine.json()["discoveries"]] == [place.id]

    kept = (await db.execute(select(Discovery))).scalars().one()
    assert kept.expires_at is None
    assert kept.guest_session_id is None
    assert client.cookies.get(GUEST_COOKIE) is None


async def test_a_guest_reads_their_own_claim_with_its_deadline(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    await client.post("/api/discoveries", json={"place_id": place.id, "caption": CAPTION})

    mine = await client.get("/api/discoveries")

    assert mine.status_code == 200
    found = mine.json()["discoveries"]
    assert [item["place_id"] for item in found] == [place.id]
    assert found[0]["expires_at"] is not None


async def test_a_visitor_who_has_claimed_nothing_gets_an_empty_list(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Not a 401: an empty answer is the truth, and the UI needs it to know
    whether the claim control should be offered or explained."""
    mine = await client.get("/api/discoveries")

    assert mine.status_code == 200
    assert mine.json()["discoveries"] == []


async def test_a_guest_cannot_vote(client: AsyncClient, db: AsyncSession) -> None:
    response = await client.post("/api/votes", json={"proposal_id": 1, "direction": "up"})

    assert response.status_code == 401


async def test_a_guest_cannot_bookmark(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)

    response = await client.post(f"/api/bookmarks/{place.id}")

    assert response.status_code == 401


async def test_a_guest_cannot_propose(client: AsyncClient, db: AsyncSession) -> None:
    place = await build_place(db)

    response = await client.post(
        "/api/proposals", json={"place_id": place.id, "text": "The Cove of Few Regrets"}
    )

    assert response.status_code == 401


async def test_a_guest_claim_is_still_screened_and_still_checked(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(_text: str) -> classifier.Categories:
        return classifier.Categories(spam=True)

    monkeypatch.setattr(classifier, "classify", refuse)
    place = await build_place(db)

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 422
    assert (await db.execute(select(Discovery))).scalars().all() == []
