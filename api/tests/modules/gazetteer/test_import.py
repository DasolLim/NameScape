from pathlib import Path

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
