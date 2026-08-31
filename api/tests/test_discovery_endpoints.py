import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import User
from app.modules.accounts import service as accounts_service
from app.modules.moderation import classifier
from tests.factories import build_place, build_user

CAPTION = "A real place, and the name is real too."


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


async def sign_in(client: AsyncClient, user: User) -> None:
    client.cookies.set("toponomicon_session", accounts_service._session_for(user).cookie)


async def test_a_place_reports_its_eligibility_and_claim_status(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await sign_in(client, user)

    response = await client.get(f"/api/places/{place.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Dildo"
    assert body["claimed_by"] is None
    assert body["eligibility"] == "allowed"


async def test_a_blocked_place_says_so_plainly_and_still_appears(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await sign_in(client, user)
    await db.execute(
        text(
            "INSERT INTO restricted_zones (geom, rule_type, reason, source) VALUES "
            "(ST_GeogFromText('SRID=4326;POLYGON((-53.6 47.5,-53.4 47.5,"
            "-53.4 47.7,-53.6 47.7,-53.6 47.5))'), 'no_nomination', 'A memorial.', 'test')"
        )
    )

    body = (await client.get(f"/api/places/{place.id}")).json()

    assert body["eligibility"] == "blocked"
    assert body["eligibility_reason"] == "A memorial."
    assert body["name"] == "Dildo"


async def test_claiming_without_an_account_is_allowed_but_expires(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Superseded Addendum A: claiming is the one write a guest may make.

    It used to be a 401. The claim is now real and locked to the visitor, and
    the deadline is what gives them a reason to create an account.
    """
    place = await build_place(db)

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] is not None


async def test_a_successful_claim_returns_the_first_finder(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")
    await sign_in(client, user)

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 201
    assert response.json()["finder"] == "firstfinder"


async def test_a_second_claim_is_a_conflict_not_a_generic_error(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    first = await build_user(db, username="firstfinder")
    second = await build_user(db, username="latecomer")
    await sign_in(client, first)
    await client.post("/api/discoveries", json={"place_id": place.id, "caption": CAPTION})

    await sign_in(client, second)
    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": CAPTION}
    )

    assert response.status_code == 409


async def test_a_caption_over_140_characters_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await sign_in(client, user)

    response = await client.post(
        "/api/discoveries", json={"place_id": place.id, "caption": "x" * 141}
    )

    assert response.status_code == 422


async def test_place_detail_reports_whether_the_viewer_saved_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    from app.models import Bookmark

    place = await build_place(db)
    user = await build_user(db, username="collector")
    await sign_in(client, user)

    before = (await client.get(f"/api/places/{place.id}")).json()
    db.add(Bookmark(user_id=user.id, place_id=place.id))
    await db.flush()
    after = (await client.get(f"/api/places/{place.id}")).json()

    assert before["bookmarked"] is False
    assert after["bookmarked"] is True


async def test_a_signed_in_user_can_list_their_own_finds(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="collector")
    await sign_in(client, user)
    await client.post("/api/discoveries", json={"place_id": place.id, "caption": CAPTION})

    response = await client.get("/api/discoveries")

    assert response.status_code == 200
    assert [d["place_name"] for d in response.json()["discoveries"]] == ["Dildo"]


async def test_listing_finds_requires_an_account(client: AsyncClient) -> None:
    assert (await client.get("/api/discoveries")).status_code == 401
