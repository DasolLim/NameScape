"""What the interface is told about an etymology, and how a reader corrects it.

The confidence has to cross the API boundary, because the one thing this
feature must never do is present a generated meaning as a sourced one. A
correction is how a reader who knows better fixes it, and it goes through the
same moderation as everything else people write.
"""

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.db import get_session
from app.main import app
from app.models import EtymologyCorrection
from app.modules.accounts import service as accounts_service
from app.modules.gazetteer.etymology import Confidence
from app.modules.moderation import classifier
from tests.factories import build_place, build_user

CORRECTION = "Welsh: ffynnon groyw, meaning clear well."


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


async def sign_in(client: AsyncClient, db: AsyncSession, username: str = "reader") -> None:
    user = await build_user(db, username=username)
    client.cookies.set("namescape_session", accounts_service._session_for(user).cookie)


async def test_a_sourced_etymology_arrives_with_its_confidence_and_source(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    place.etymology = "The name derives from the Old English."
    place.etymology_confidence = Confidence.HIGH
    place.etymology_source = "https://en.wikipedia.org/wiki/Dildo"
    await db.flush()

    detail = (await client.get(f"/api/places/{place.id}")).json()

    assert detail["etymology"] == "The name derives from the Old English."
    assert detail["etymology_confidence"] == "high"
    assert detail["etymology_source"] == "https://en.wikipedia.org/wiki/Dildo"


async def test_a_generated_etymology_says_so(client: AsyncClient, db: AsyncSession) -> None:
    """The interface cannot present this as sourced, so it has to be told."""
    place = await build_place(db)
    place.etymology = "Possibly from a word for a pin."
    place.etymology_confidence = Confidence.UNVERIFIED
    place.etymology_source = "anthropic/claude-opus-5"
    await db.flush()

    detail = (await client.get(f"/api/places/{place.id}")).json()

    assert detail["etymology_confidence"] == "unverified"


async def test_an_unresolved_place_reports_no_confidence_rather_than_failing(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)

    detail = (await client.get(f"/api/places/{place.id}")).json()

    assert detail["etymology"] is None
    assert detail["etymology_confidence"] is None


async def test_a_place_carries_the_language_its_name_is_probably_in(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The reveal is offered on names the reader probably cannot read. Deciding
    that needs the name's language, and the language table stays server-side."""
    welsh = await build_place(db, name="Ffynnongroyw", geonames_id=2_650_100, country_code="GB")
    russian = await build_place(db, name="Bolboda", geonames_id=600_300, country_code="RU")
    nowhere = await build_place(db, name="Zzyzx", geonames_id=600_301, country_code=None)

    assert (await client.get(f"/api/places/{welsh.id}")).json()["name_language"] == "en"
    assert (await client.get(f"/api/places/{russian.id}")).json()["name_language"] == "ru"
    assert (await client.get(f"/api/places/{nowhere.id}")).json()["name_language"] is None


async def test_a_correction_is_accepted_and_held_for_review(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    await sign_in(client, db)

    response = await client.post(f"/api/places/{place.id}/etymology", json={"text": CORRECTION})

    assert response.status_code == 201
    stored = (await db.execute(select(EtymologyCorrection))).scalars().one()
    assert stored.text == CORRECTION
    # Held, not applied: a correction is a claim about the world, and the row
    # it would replace is cited. A person decides.
    assert stored.status == "pending"
    assert (await db.get(type(place), place.id)).etymology is None  # type: ignore[union-attr]


async def test_a_correction_goes_through_the_same_moderation_as_anything_else(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(_text: str) -> classifier.Categories:
        return classifier.Categories(spam=True)

    monkeypatch.setattr(classifier, "classify", refuse)
    place = await build_place(db)
    await sign_in(client, db)

    response = await client.post(f"/api/places/{place.id}/etymology", json={"text": CORRECTION})

    assert response.status_code == 422
    assert (await db.execute(select(EtymologyCorrection))).scalars().all() == []


async def test_a_correction_needs_an_account_because_the_credit_does(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)

    response = await client.post(f"/api/places/{place.id}/etymology", json={"text": CORRECTION})

    assert response.status_code == 401


async def test_a_correction_to_a_place_that_does_not_exist_is_a_404(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db)

    response = await client.post("/api/places/999999/etymology", json={"text": CORRECTION})

    assert response.status_code == 404


async def test_one_person_cannot_file_the_same_correction_twice(
    client: AsyncClient, db: AsyncSession
) -> None:
    place = await build_place(db)
    await sign_in(client, db)

    first = await client.post(f"/api/places/{place.id}/etymology", json={"text": CORRECTION})
    again = await client.post(f"/api/places/{place.id}/etymology", json={"text": CORRECTION})

    assert first.status_code == 201
    assert again.status_code == 409
    assert len((await db.execute(select(EtymologyCorrection))).scalars().all()) == 1
