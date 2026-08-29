import asyncio
import inspect
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Discovery
from app.modules import discoveries
from app.modules.discoveries import service
from app.modules.moderation import classifier
from tests.factories import build_place, build_user

CAPTION = "Found on a map, laughed for a full minute."


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


async def test_claiming_an_unclaimed_place_credits_the_finder(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")

    discovery = await discoveries.claim(db, place.id, user.id, CAPTION)

    assert discovery.place_id == place.id
    assert discovery.user_id == user.id
    assert discovery.caption == CAPTION


async def test_claiming_a_claimed_place_is_a_clear_conflict(db: AsyncSession) -> None:
    place = await build_place(db)
    first = await build_user(db, username="firstfinder")
    second = await build_user(db, username="latecomer")
    await discoveries.claim(db, place.id, first.id, CAPTION)

    with pytest.raises(service.AlreadyClaimedError):
        await discoveries.claim(db, place.id, second.id, CAPTION)


async def test_an_ineligible_place_is_rejected_before_the_classifier_runs(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not spend a classifier call on a place that cannot be claimed."""
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await db.execute(
        text(
            "INSERT INTO restricted_zones (geom, rule_type, reason, source) VALUES "
            "(ST_GeogFromText('SRID=4326;POLYGON((-53.6 47.5,-53.4 47.5,"
            "-53.4 47.7,-53.6 47.7,-53.6 47.5))'), 'no_nomination', 'A memorial.', 'test')"
        )
    )

    calls = 0

    async def counted(_text: str) -> classifier.Categories:
        nonlocal calls
        calls += 1
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", counted)

    with pytest.raises(service.NotEligibleError):
        await discoveries.claim(db, place.id, user.id, CAPTION)

    assert calls == 0


async def test_a_rejected_caption_leaves_no_orphan_discovery(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")

    async def flags_spam(_text: str) -> classifier.Categories:
        return classifier.Categories(spam=True)

    monkeypatch.setattr(classifier, "classify", flags_spam)

    with pytest.raises(service.CaptionRejectedError):
        await discoveries.claim(db, place.id, user.id, "buy cheap maps dot com")

    assert await db.scalar(select(func.count()).select_from(Discovery)) == 0


async def test_for_user_lists_newest_first(db: AsyncSession) -> None:
    user = await build_user(db, username="collector")
    for index, name in enumerate(("Dildo", "Boring", "Dull")):
        place = await build_place(db, name=name, geonames_id=900_000 + index)
        await discoveries.claim(db, place.id, user.id, CAPTION)

    found = await discoveries.for_user(db, user.id)

    assert [entry.place_name for entry in found] == ["Dull", "Boring", "Dildo"]


async def test_list_in_bounds_caps_at_five_hundred(db: AsyncSession) -> None:
    user = await build_user(db, username="prolific")
    for index in range(service.MAX_FEATURES + 10):
        place = await build_place(
            db,
            name=f"Place {index}",
            geonames_id=800_000 + index,
            lon=-53.5 + index * 0.0001,
            lat=47.5,
        )
        await build_discoveryless_claim(db, place.id, user.id)

    pins = await discoveries.list_in_bounds(db, service.BBox(-54.0, 47.0, -53.0, 48.0), zoom=12)

    assert len(pins) == service.MAX_FEATURES


async def build_discoveryless_claim(session: AsyncSession, place_id: int, user_id: UUID) -> None:
    """Insert straight to the table: this test is about the cap, not the pipeline."""
    session.add(Discovery(place_id=place_id, user_id=user_id, caption=CAPTION))
    await session.flush()


async def test_two_concurrent_claims_leave_exactly_one_winner(test_database: str) -> None:
    """A real race across two transactions. The unique constraint is what makes
    first-finder credit mean anything, so it is proven, not assumed."""
    engine = create_async_engine(test_database, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as setup:
        place = await build_place(setup, name="Contested", geonames_id=700_001)
        first = await build_user(setup, username="racer_one")
        second = await build_user(setup, username="racer_two")
        await setup.commit()
        place_id, first_id, second_id = place.id, first.id, second.id

    async def attempt(user_id: UUID) -> str:
        async with maker() as session:
            try:
                await discoveries.claim(session, place_id, user_id, CAPTION)
                await session.commit()
            except Exception as error:
                await session.rollback()
                return type(error).__name__
            return "won"

    try:
        outcomes = await asyncio.gather(attempt(first_id), attempt(second_id))

        assert sorted(outcomes) == ["AlreadyClaimedError", "won"]

        async with maker() as check:
            total = await check.scalar(
                select(func.count()).select_from(Discovery).where(Discovery.place_id == place_id)
            )
        assert total == 1
    finally:
        async with maker() as cleanup:
            await cleanup.execute(
                text("DELETE FROM discoveries WHERE place_id = :p"), {"p": place_id}
            )
            await cleanup.execute(text("DELETE FROM places WHERE id = :p"), {"p": place_id})
            await cleanup.execute(
                text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": [first_id, second_id]}
            )
            await cleanup.commit()
        await engine.dispose()


def test_the_module_exposes_exactly_three_public_functions() -> None:
    public = [
        name
        for name, value in vars(discoveries).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["claim", "for_user", "list_in_bounds"]
