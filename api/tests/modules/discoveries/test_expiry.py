"""Expired guest claims release the place.

The deadline has to be real or it is not a deadline. Releasing is a delete: no
first-finder credit was ever awarded, so there is nothing to take back.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery, Place
from app.modules import discoveries
from app.modules.accounts import guests
from app.modules.discoveries import expiry
from app.modules.moderation import classifier
from tests.factories import build_guest_session, build_place, build_user

CAPTION = "Found on a map, laughed for a full minute."


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


async def guest_claim(db: AsyncSession, *, expires_in: timedelta, **place: object) -> int:
    place_row = await build_place(db, **place)  # type: ignore[arg-type]
    guest = await build_guest_session(db)
    discovery = await discoveries.claim(
        db, place_row.id, discoveries.GuestClaimant(guest.id), CAPTION
    )
    discovery.expires_at = datetime.now(UTC) + expires_in
    await db.flush()
    return place_row.id


async def test_an_expired_claim_releases_the_place(db: AsyncSession) -> None:
    place_id = await guest_claim(db, expires_in=timedelta(seconds=-1))

    released = await expiry.release_expired(db)

    assert released == 1
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 0
    # The place itself is untouched: it is gazetteer data, not a claim.
    assert await db.get(Place, place_id) is not None


async def test_a_claim_still_inside_its_week_is_left_alone(db: AsyncSession) -> None:
    await guest_claim(db, expires_in=timedelta(days=6))

    assert await expiry.release_expired(db) == 0
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 1


async def test_a_second_run_changes_nothing(db: AsyncSession) -> None:
    await guest_claim(db, expires_in=timedelta(seconds=-1))
    await expiry.release_expired(db)

    assert await expiry.release_expired(db) == 0


async def test_a_user_claim_is_never_released(db: AsyncSession) -> None:
    """A user claim has no expiry, and the job must not invent one."""
    place = await build_place(db)
    user = await build_user(db, username="firstfinder")
    await discoveries.claim(db, place.id, discoveries.UserClaimant(user.id), CAPTION)

    assert await expiry.release_expired(db) == 0
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 1


async def test_a_claim_merged_a_minute_before_expiry_survives(db: AsyncSession) -> None:
    """The merge clears expires_at, which is what puts it out of reach."""
    place = await build_place(db)
    guest = await build_guest_session(db)
    user = await build_user(db, username="justintime")
    discovery = await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)
    discovery.expires_at = datetime.now(UTC) + timedelta(minutes=1)
    await db.flush()

    await guests.merge(db, guests.cookie_for(guest.id), user)
    # Well past the deadline it would have had.
    assert await expiry.release_expired(db) == 0

    kept = (await db.execute(select(Discovery))).scalars().one()
    assert kept.user_id == user.id
    assert kept.expires_at is None


async def test_releasing_leaves_the_place_claimable_again(db: AsyncSession) -> None:
    place_id = await guest_claim(db, expires_in=timedelta(seconds=-1))
    await expiry.release_expired(db)
    latecomer = await build_user(db, username="latecomer")

    discovery = await discoveries.claim(
        db, place_id, discoveries.UserClaimant(latecomer.id), CAPTION
    )

    assert discovery.user_id == latecomer.id
