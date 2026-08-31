from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place
from app.modules.gazetteer.importer import import_geonames

FIXTURE = Path(__file__).parents[2] / "fixtures" / "geonames_sample.txt"


async def place_named(session: AsyncSession, name: str) -> Place:
    place = (await session.execute(select(Place).where(Place.name == name))).scalars().first()
    assert place is not None, f"{name} was not imported"
    return place


async def test_imports_a_row_with_its_identity_and_position(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    dildo = await place_named(db, "Dildo")
    point = await db.scalar(select(func.ST_AsText(Place.centroid)).where(Place.id == dildo.id))

    assert dildo.geonames_id == 6942553
    assert dildo.feature_class == "P"
    assert dildo.feature_code == "PPL"
    assert dildo.country_code == "CA"
    assert point == "POINT(-53.5442 47.5766)"


async def test_reimporting_updates_rather_than_duplicating(db: AsyncSession) -> None:
    first = await import_geonames(db, FIXTURE)
    second = await import_geonames(db, FIXTURE)

    total = await db.scalar(select(func.count()).select_from(Place))

    assert first == second
    assert total == first


async def test_only_populated_hydro_and_terrain_are_imported(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    classes = set((await db.execute(select(Place.feature_class))).scalars().all())
    names = set((await db.execute(select(Place.name))).scalars().all())

    assert classes == {"P", "H", "T"}
    assert "United States" not in names
    assert "Yosemite National Park" not in names


async def test_tier_follows_significance(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    assert (await place_named(db, "Tokyo")).tier == 1
    assert (await place_named(db, "Atlantic Ocean")).tier == 1
    assert (await place_named(db, "Batman")).tier == 2
    assert (await place_named(db, "Lake Superior")).tier == 2
    assert (await place_named(db, "Dildo")).tier == 3
    assert (await place_named(db, "Bloody Dick Creek")).tier == 3


async def test_alternate_names_are_parsed_into_the_array(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    fugging = await place_named(db, "Fugging")

    assert fugging.alternate_names == ["Fucking", "Fugging"]
    assert fugging.name_normalized == "fugging"


async def test_rows_are_written_in_batches_not_one_at_a_time(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A per-row round trip cannot survive a real dump of millions of rows."""
    from app.modules.gazetteer import importer

    executed = 0
    original = db.execute

    async def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal executed
        executed += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(db, "execute", counting)
    monkeypatch.setattr(importer, "BATCH_SIZE", 20)

    imported = await import_geonames(db, FIXTURE)

    assert imported == 41
    # 41 rows in batches of 20 is three statements, not forty-one.
    assert executed <= 3


def test_admin_codes_resolve_to_readable_names() -> None:
    """GeoNames gives some countries numeric admin1 codes. "05 - CA" tells a
    user nothing; "Newfoundland and Labrador" does."""
    from app.modules.gazetteer import regions

    lookup = regions.parse(
        "CA.05\tNewfoundland and Labrador\tNewfoundland and Labrador\t6354959\n"
        "US.FL\tFlorida\tFlorida\t4155751\n"
    )

    assert lookup == {("CA", "05"): "Newfoundland and Labrador", ("US", "FL"): "Florida"}
    assert regions.name_for(lookup, "CA", "05") == "Newfoundland and Labrador"
    # An unknown pair falls back to the raw code rather than blanking it.
    assert regions.name_for(lookup, "GB", "ENG") == "ENG"
    assert regions.name_for(lookup, None, None) is None


async def test_a_class_filter_keeps_settlements_and_drops_the_rest(db: AsyncSession) -> None:
    """Storage, not taste. The US dump alone is 470MB, and 381MB of that is
    half a million lakes and a quarter million hills that nobody looks up.
    Importing its populated places keeps Boring, Oregon and fits a free tier.
    """
    imported = await import_geonames(db, FIXTURE, feature_classes={"P"})

    rows = (
        await db.execute(select(Place.feature_class, func.count()).group_by(Place.feature_class))
    ).all()

    assert imported > 0
    assert {feature_class for feature_class, _ in rows} == {"P"}


async def test_no_filter_imports_everything(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    classes = (await db.execute(select(Place.feature_class).distinct())).scalars().all()

    assert len(set(classes)) > 1
