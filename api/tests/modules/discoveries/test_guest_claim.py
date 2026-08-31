"""A guest claim is real, and it expires.

A provisional claim that anyone could take at any moment is not worth
protecting, so nothing about it makes a visitor want an account. A claim with
a deadline is both genuinely theirs and genuinely at risk.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import Discovery, GuestSession
from app.modules import discoveries
from app.modules.discoveries import service
from app.modules.moderation import classifier
from tests.factories import build_guest_session, build_place, build_user

CAPTION = "Found on a map, laughed for a full minute."


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


async def test_a_guest_can_claim_a_place(db: AsyncSession) -> None:
    place = await build_place(db)
    guest = await build_guest_session(db)

    discovery = await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)

    assert discovery.place_id == place.id
    assert discovery.claimant_type == "guest"
    assert discovery.guest_session_id == guest.id
    assert discovery.user_id is None


async def test_a_guest_gets_exactly_one_claim(db: AsyncSession) -> None:
    """The limit is on the guest session, not on the person."""
    first = await build_place(db)
    second = await build_place(db, name="Boring", geonames_id=5_713_376)
    guest = await build_guest_session(db)
    await discoveries.claim(db, first.id, discoveries.GuestClaimant(guest.id), CAPTION)

    with pytest.raises(service.GuestLimitReachedError):
        await discoveries.claim(db, second.id, discoveries.GuestClaimant(guest.id), CAPTION)


async def test_a_guest_claim_expires_in_seven_days(db: AsyncSession) -> None:
    place = await build_place(db)
    guest = await build_guest_session(db)

    discovery = await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)

    assert discovery.expires_at is not None
    remaining = discovery.expires_at - datetime.now(UTC)
    assert timedelta(days=6, hours=23) < remaining <= timedelta(days=7)


async def test_a_user_claim_never_expires(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")

    discovery = await discoveries.claim(db, place.id, discoveries.UserClaimant(user.id), CAPTION)

    assert discovery.claimant_type == "user"
    assert discovery.expires_at is None
    assert discovery.guest_session_id is None


async def test_the_database_refuses_a_guest_claim_with_no_expiry(db: AsyncSession) -> None:
    """The invalid state is unrepresentable, not merely discouraged in code."""
    place = await build_place(db)
    guest = await build_guest_session(db)

    with pytest.raises(IntegrityError):
        await db.execute(
            text(
                "INSERT INTO discoveries (place_id, claimant_type, guest_session_id, caption) "
                "VALUES (:place_id, 'guest', :guest_id, :caption)"
            ),
            {"place_id": place.id, "guest_id": guest.id, "caption": CAPTION},
        )


async def test_the_database_refuses_a_user_claim_that_expires(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")

    with pytest.raises(IntegrityError):
        await db.execute(
            text(
                "INSERT INTO discoveries "
                "(place_id, claimant_type, user_id, caption, expires_at) "
                "VALUES (:place_id, 'user', :user_id, :caption, now())"
            ),
            {"place_id": place.id, "user_id": user.id, "caption": CAPTION},
        )


async def test_the_database_refuses_a_claim_with_two_claimants(db: AsyncSession) -> None:
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")
    guest = await build_guest_session(db)

    with pytest.raises(IntegrityError):
        await db.execute(
            text(
                "INSERT INTO discoveries "
                "(place_id, claimant_type, user_id, guest_session_id, caption) "
                "VALUES (:place_id, 'user', :user_id, :guest_id, :caption)"
            ),
            {
                "place_id": place.id,
                "user_id": user.id,
                "guest_id": guest.id,
                "caption": CAPTION,
            },
        )


async def test_a_guest_caption_goes_through_the_same_moderation(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(_text: str) -> classifier.Categories:
        return classifier.Categories(spam=True)

    monkeypatch.setattr(classifier, "classify", refuse)
    place = await build_place(db)
    guest = await build_guest_session(db)

    with pytest.raises(service.CaptionRejectedError):
        await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)


async def test_a_guest_faces_the_same_eligibility_rules(db: AsyncSession) -> None:
    place = await build_place(db)
    guest = await build_guest_session(db)
    await db.execute(
        text(
            "INSERT INTO restricted_zones (geom, rule_type, reason, source) VALUES "
            "(ST_GeogFromText('SRID=4326;POLYGON((-53.6 47.5,-53.4 47.5,"
            "-53.4 47.7,-53.6 47.7,-53.6 47.5))'), 'no_nomination', 'A memorial.', 'test')"
        )
    )

    with pytest.raises(service.NotEligibleError):
        await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)


async def test_a_guest_pin_still_draws_on_the_globe(db: AsyncSession) -> None:
    """A claim nobody can see is not worth converting for."""
    place = await build_place(db)
    guest = await build_guest_session(db)
    await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)

    pins = await discoveries.list_in_bounds(db, service.BBox(-54.0, 47.0, -53.0, 48.0), zoom=12)

    assert [pin.place_id for pin in pins] == [place.id]
    assert pins[0].finder == service.GUEST_FINDER


async def test_a_guest_and_a_user_racing_for_one_place_leave_a_single_claim(
    test_database: str,
) -> None:
    """Committed concurrently, the unique constraint is the only arbiter."""
    engine = create_async_engine(test_database, poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    place_id: int
    user_id: UUID
    guest_id: UUID
    async with maker() as setup:
        # These rows are committed, outside the rolled-back fixture, so a run
        # that died before its cleanup would otherwise poison every run after.
        await setup.execute(text("DELETE FROM places WHERE geonames_id = 9100001"))
        await setup.execute(text("DELETE FROM users WHERE username = 'racer'"))
        place = await build_place(setup, name="Contested", geonames_id=9_100_001)
        user = await build_user(setup, username="racer")
        guest = await build_guest_session(setup)
        await setup.commit()
        place_id, user_id, guest_id = place.id, user.id, guest.id

    async def attempt(claimant: service.Claimant) -> bool:
        async with maker() as session:
            try:
                await discoveries.claim(session, place_id, claimant, CAPTION)
                await session.commit()
            except (service.AlreadyClaimedError, IntegrityError):
                return False
            return True

    try:
        outcomes = await asyncio.gather(
            attempt(service.UserClaimant(user_id)),
            attempt(service.GuestClaimant(guest_id)),
            return_exceptions=True,
        )
        assert sum(1 for outcome in outcomes if outcome is True) == 1

        async with maker() as check:
            rows = (
                (await check.execute(select(Discovery).where(Discovery.place_id == place_id)))
                .scalars()
                .all()
            )
            assert len(rows) == 1
    finally:
        async with maker() as cleanup:
            await cleanup.execute(
                text("DELETE FROM discoveries WHERE place_id = :p"), {"p": place_id}
            )
            await cleanup.execute(text("DELETE FROM places WHERE id = :p"), {"p": place_id})
            await cleanup.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            await cleanup.execute(text("DELETE FROM guest_sessions WHERE id = :g"), {"g": guest_id})
            await cleanup.commit()
        await engine.dispose()


async def test_an_unknown_guest_session_cannot_hold_a_claim(db: AsyncSession) -> None:
    """A forged cookie names a row that does not exist, and the FK says so."""
    place = await build_place(db)

    with pytest.raises(IntegrityError):
        await discoveries.claim(db, place.id, discoveries.GuestClaimant(uuid4()), CAPTION)


async def test_a_guest_session_row_records_when_it_was_opened(db: AsyncSession) -> None:
    guest = await build_guest_session(db)

    stored = await db.get(GuestSession, guest.id)

    assert stored is not None
    assert stored.merged_into is None
    assert stored.merged_at is None
