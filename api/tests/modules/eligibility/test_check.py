import inspect

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RestrictedZone
from app.modules import eligibility
from app.modules.eligibility import service
from tests.factories import build_place, build_user

# A small square around Dildo, Newfoundland.
AROUND_DILDO = (
    "SRID=4326;POLYGON((-53.60 47.53, -53.48 47.53, -53.48 47.62, -53.60 47.62, -53.60 47.53))"
)


async def zone(session: AsyncSession, rule_type: str, reason: str) -> RestrictedZone:
    restricted = RestrictedZone(
        geom=AROUND_DILDO, rule_type=rule_type, reason=reason, source="test"
    )
    session.add(restricted)
    await session.flush()
    return restricted


async def test_a_place_in_a_no_nomination_zone_is_blocked_with_a_plain_reason(
    db: AsyncSession,
) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await zone(db, "no_nomination", "This is a war memorial.")

    verdict = await eligibility.check(db, place.id, user.id)

    assert verdict.status is service.Eligibility.BLOCKED
    assert verdict.reason == "This is a war memorial."


async def test_a_place_in_an_etymology_zone_requires_an_etymology(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")
    await zone(db, "etymology_required", "Indigenous toponym.")

    verdict = await eligibility.check(db, place.id, user.id)

    assert verdict.status is service.Eligibility.ETYMOLOGY_REQUIRED


async def test_an_ordinary_place_with_no_zone_is_allowed(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="finder")

    verdict = await eligibility.check(db, place.id, user.id)

    assert verdict.status is service.Eligibility.ALLOWED


async def test_a_name_in_another_language_requires_an_etymology(db: AsyncSession) -> None:
    """Tier B: the highest-leverage rule in the policy."""
    place = await build_place(db, name="Ffynnongroyw", geonames_id=2651739, country_code="GB")
    welsh_place = await build_place(
        db, name="Bolshoye Boldino", geonames_id=2028462, country_code="RU"
    )
    user = await build_user(db, username="english")

    assert (await eligibility.check(db, place.id, user.id)).status is service.Eligibility.ALLOWED
    assert (
        await eligibility.check(db, welsh_place.id, user.id)
    ).status is service.Eligibility.ETYMOLOGY_REQUIRED


async def test_an_unknown_place_is_blocked_rather_than_raising(db: AsyncSession) -> None:
    user = await build_user(db, username="finder")

    verdict = await eligibility.check(db, 999_999, user.id)

    assert verdict.status is service.Eligibility.BLOCKED


async def test_the_zone_lookup_can_use_the_gist_index(db: AsyncSession) -> None:
    await build_place(db)
    # With a handful of rows the planner would seq-scan regardless; disabling
    # it proves the index exists and is usable for this predicate.
    await db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (
        (await db.execute(text(f"EXPLAIN {service.ZONE_LOOKUP_SQL}"), {"place_id": 1}))
        .scalars()
        .all()
    )

    assert any("idx_restricted_zones_geom" in line for line in plan)


def test_the_module_exposes_exactly_one_public_function() -> None:
    public = [
        name
        for name, value in vars(eligibility).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert public == ["check"]
