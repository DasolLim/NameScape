import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery
from app.modules import accounts
from tests.factories import build_place, build_user


async def stock_gazetteer(session: AsyncSession) -> None:
    """Four Canadian places and one British, so completion has a denominator."""
    for index in range(4):
        await build_place(
            session, name=f"CA {index}", geonames_id=110_000 + index, country_code="CA"
        )
    await build_place(session, name="GB 0", geonames_id=120_000, country_code="GB")


async def test_country_completion_is_finds_over_places_in_that_country(
    db: AsyncSession,
) -> None:
    await stock_gazetteer(db)
    user = await build_user(db, username="collector")
    canadian = await build_place(db, name="CA 4", geonames_id=110_004, country_code="CA")
    db.add(Discovery(place_id=canadian.id, user_id=user.id, caption="found"))
    await db.flush()

    passport = await accounts.passport(db, "collector")

    assert passport is not None
    # One of five Canadian places.
    assert passport.completion["CA"] == pytest.approx(0.2)
    assert "GB" not in passport.completion


async def test_the_hero_number_is_the_first_finder_count(db: AsyncSession) -> None:
    await stock_gazetteer(db)
    user = await build_user(db, username="collector")
    for index in range(3):
        place = await build_place(db, name=f"F {index}", geonames_id=130_000 + index)
        db.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await db.flush()

    passport = await accounts.passport(db, "collector")

    assert passport is not None
    # Every discovery is a first find: the unique constraint on place_id makes
    # a second one impossible, so the two counts cannot diverge.
    assert passport.first_finds == passport.discoveries == 3


async def test_an_empty_passport_is_not_an_error(db: AsyncSession) -> None:
    await build_user(db, username="newcomer")

    passport = await accounts.passport(db, "newcomer")

    assert passport is not None
    assert passport.discoveries == 0
    assert passport.completion == {}
