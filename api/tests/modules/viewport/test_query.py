import inspect

from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bookmark, Discovery
from app.modules import viewport
from app.modules.viewport import service
from tests.factories import build_place, build_user

NEWFOUNDLAND = service.BBox(west=-54.0, south=47.0, east=-53.0, north=48.0)


async def seed(session: AsyncSession, count: int = 3) -> None:
    user = await build_user(session, username="finder")
    for index in range(count):
        place = await build_place(
            session,
            name=f"Place {index}",
            geonames_id=500_000 + index,
            # Kept tight so every seeded place stays inside NEWFOUNDLAND.
            lon=-53.5 + index * 0.0001,
            lat=47.5,
        )
        session.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await session.flush()


async def test_a_small_pan_reuses_the_same_cache_key(db: AsyncSession) -> None:
    """Without snapping, every pixel of movement is a cache miss."""
    original = service.BBox(-53.500, 47.500, -53.400, 47.600)
    nudged = service.BBox(-53.499, 47.501, -53.399, 47.601)

    assert service.cache_key(original, zoom=10) == service.cache_key(nudged, zoom=10)


async def test_a_real_pan_changes_the_cache_key(db: AsyncSession) -> None:
    here = service.BBox(-53.5, 47.5, -53.4, 47.6)
    far = service.BBox(-40.0, 47.5, -39.9, 47.6)

    assert service.cache_key(here, zoom=10) != service.cache_key(far, zoom=10)


async def test_zoom_bands_return_the_documented_shape(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    await seed(db)

    planet = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=2)
    middle = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=6)
    close = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12)

    assert planet.band is service.Band.COUNTRY
    assert planet.features[0].country_code == "CA"
    assert planet.features[0].count == 3

    assert middle.band is service.Band.CLUSTER
    assert sum(feature.count for feature in middle.features) == 3

    assert close.band is service.Band.PIN
    assert {feature.name for feature in close.features} == {"Place 0", "Place 1", "Place 2"}
    assert close.features[0].finder == "finder"


async def test_a_cache_hit_returns_the_same_payload_as_a_miss(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    await seed(db)

    miss = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12)
    hit = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12)

    assert hit == miss
    assert await fake_redis.exists(service.cache_key(NEWFOUNDLAND, zoom=12))


async def test_the_result_is_capped(db: AsyncSession, fake_redis: FakeRedis) -> None:
    await seed(db, count=service.MAX_FEATURES + 5)

    result = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12)

    assert len(result.features) == service.MAX_FEATURES


async def test_bookmarks_appear_only_for_a_signed_in_viewer(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    await seed(db)
    viewer = await build_user(db, username="collector")
    place = await build_place(db, name="Saved", geonames_id=400_001, lon=-53.45, lat=47.55)
    db.add(Bookmark(user_id=viewer.id, place_id=place.id))
    await db.flush()

    anonymous = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12)
    signed_in = await viewport.query(db, fake_redis, NEWFOUNDLAND, zoom=12, user_id=viewer.id)

    assert anonymous.bookmarks == []
    assert [feature.name for feature in signed_in.bookmarks] == ["Saved"]


def test_the_module_exposes_exactly_one_public_function() -> None:
    public = [
        name
        for name, value in vars(viewport).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert public == ["query"]


async def test_a_planet_wide_box_does_not_trip_the_antipodal_edge(
    db: AsyncSession, fake_redis: FakeRedis
) -> None:
    """A geography edge cannot span 180 degrees; at planet zoom the box does."""
    await seed(db)
    whole_world = service.BBox(west=-159.0, south=-56.7, east=159.2, north=73.3)

    result = await viewport.query(db, fake_redis, whole_world, zoom=2)

    assert result.band is service.Band.COUNTRY
    assert result.features[0].country_code == "CA"
