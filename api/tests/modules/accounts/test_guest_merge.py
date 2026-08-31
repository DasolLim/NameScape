"""Signing up keeps the claim you already made.

The merge runs inside authenticate(), so no caller ever orchestrates it. A
visitor who has to re-find their own place has been told the deadline was a
threat rather than a promise.
"""

import inspect

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery, GuestSession, User
from app.modules import accounts, discoveries
from app.modules.accounts import delivery, guests
from app.modules.moderation import classifier
from tests.factories import build_guest_session, build_place, build_user

CAPTION = "Found on a map, laughed for a full minute."


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    outbox: list[tuple[str, str]] = []

    async def capture(email: str, token: str) -> None:
        outbox.append((email, token))

    monkeypatch.setattr(delivery, "send_magic_link", capture)
    return outbox


async def claim_as_guest(db: AsyncSession, **place_kwargs: object) -> tuple[GuestSession, str]:
    """A guest with one claim, and the cookie that proves it is theirs."""
    place = await build_place(db, **place_kwargs)  # type: ignore[arg-type]
    guest = await build_guest_session(db)
    await discoveries.claim(db, place.id, discoveries.GuestClaimant(guest.id), CAPTION)
    return guest, guests.cookie_for(guest.id)


async def test_signing_up_transfers_the_guest_claim(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    _, cookie = await claim_as_guest(db)
    await accounts.request_magic_link(db, fake_redis, "new@example.test")

    session = await accounts.authenticate(db, sent[0][1], guest_cookie=cookie)

    assert session is not None
    discovery = (await db.execute(select(Discovery))).scalars().one()
    assert discovery.user_id == session.user_id
    assert discovery.claimant_type == "user"
    assert discovery.guest_session_id is None
    assert discovery.expires_at is None


async def test_the_merged_session_records_where_it_went(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    guest, cookie = await claim_as_guest(db)
    await accounts.request_magic_link(db, fake_redis, "new@example.test")

    session = await accounts.authenticate(db, sent[0][1], guest_cookie=cookie)

    assert session is not None
    merged = await db.get(GuestSession, guest.id)
    assert merged is not None
    assert merged.merged_into == session.user_id
    assert merged.merged_at is not None


async def test_the_merge_is_idempotent(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    """A retried sign-in must not transfer twice, and must not raise."""
    guest, cookie = await claim_as_guest(db)
    await accounts.request_magic_link(db, fake_redis, "twice@example.test")
    first = await accounts.authenticate(db, sent[0][1], guest_cookie=cookie)
    assert first is not None
    merged_at = (await db.get(GuestSession, guest.id)).merged_at  # type: ignore[union-attr]

    # The magic link is spent, so the second pass arrives with the cookie the
    # first one issued, which is the shape a page reload actually takes.
    again = await accounts.authenticate(db, first.cookie, guest_cookie=cookie)

    assert again is not None
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 1
    assert (await db.get(GuestSession, guest.id)).merged_at == merged_at  # type: ignore[union-attr]


async def test_signing_in_to_an_existing_account_merges_into_it(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    """No duplicate account: a user may hold many discoveries."""
    existing = await build_user(db, username="veteran", email="veteran@example.test")
    already = await build_place(db, name="Dull", geonames_id=2_650_752)
    await discoveries.claim(db, already.id, discoveries.UserClaimant(existing.id), CAPTION)
    _, cookie = await claim_as_guest(db, name="Boring", geonames_id=5_713_376)
    await accounts.request_magic_link(db, fake_redis, "veteran@example.test")

    session = await accounts.authenticate(db, sent[0][1], guest_cookie=cookie)

    assert session is not None
    assert session.user_id == existing.id
    assert await db.scalar(select(func.count()).select_from(User)) == 1
    mine = await discoveries.for_user(db, discoveries.UserClaimant(existing.id))
    assert {found.place_name for found in mine} == {"Dull", "Boring"}


async def test_a_guest_session_with_no_claim_merges_cleanly(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    guest = await build_guest_session(db)
    await accounts.request_magic_link(db, fake_redis, "empty@example.test")

    session = await accounts.authenticate(db, sent[0][1], guest_cookie=guests.cookie_for(guest.id))

    assert session is not None
    assert await db.scalar(select(func.count()).select_from(Discovery)) == 0


async def test_a_forged_or_unknown_guest_cookie_is_ignored(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    """Sign-in must succeed regardless: the cookie is not a credential."""
    await accounts.request_magic_link(db, fake_redis, "forged@example.test")

    session = await accounts.authenticate(db, sent[0][1], guest_cookie="not-a-signed-cookie")

    assert session is not None


async def test_a_merged_guest_session_does_not_get_a_second_claim(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    """The transferred row no longer names the session, so merged_into is the
    only remaining record that this guest already had their one claim."""
    guest, cookie = await claim_as_guest(db)
    await accounts.request_magic_link(db, fake_redis, "greedy@example.test")
    await accounts.authenticate(db, sent[0][1], guest_cookie=cookie)
    another = await build_place(db, name="Boring", geonames_id=5_713_376)

    with pytest.raises(discoveries.GuestLimitReachedError):
        await discoveries.claim(db, another.id, discoveries.GuestClaimant(guest.id), CAPTION)


def test_the_module_still_exposes_exactly_four_public_functions() -> None:
    public = [
        name
        for name, value in vars(accounts).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["authenticate", "passport", "profile", "request_magic_link"]
