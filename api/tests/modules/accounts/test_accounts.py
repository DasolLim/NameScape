import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import accounts
from app.modules.accounts import delivery, usernames
from app.modules.gazetteer.importer import import_geonames
from tests.factories import build_discovery, build_user

FIXTURE = Path(__file__).parents[2] / "fixtures" / "geonames_sample.txt"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Capture magic links instead of mailing them."""
    outbox: list[tuple[str, str]] = []

    async def capture(email: str, token: str) -> None:
        outbox.append((email, token))

    monkeypatch.setattr(delivery, "send_magic_link", capture)
    return outbox


async def test_a_magic_link_token_works_once(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    await accounts.request_magic_link(db, fake_redis, "finder@example.test")
    _, token = sent[0]

    session = await accounts.authenticate(db, token)
    assert session is not None

    assert await accounts.authenticate(db, token) is None


async def test_a_token_older_than_fifteen_minutes_is_rejected(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    await accounts.request_magic_link(db, fake_redis, "slow@example.test")
    _, token = sent[0]

    from app.models import MagicLink

    link = (await db.execute(__import__("sqlalchemy").select(MagicLink))).scalars().one()
    link.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.flush()

    assert await accounts.authenticate(db, token) is None


async def test_the_session_cookie_authenticates_on_later_requests(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    await accounts.request_magic_link(db, fake_redis, "returning@example.test")
    first = await accounts.authenticate(db, sent[0][1])
    assert first is not None

    again = await accounts.authenticate(db, first.cookie)

    assert again is not None
    assert again.user_id == first.user_id


async def test_only_three_magic_links_per_email_per_hour(
    db: AsyncSession, fake_redis: FakeRedis, sent: list[tuple[str, str]]
) -> None:
    for _ in range(3):
        await accounts.request_magic_link(db, fake_redis, "eager@example.test")

    with pytest.raises(accounts.TooManyRequestsError):
        await accounts.request_magic_link(db, fake_redis, "eager@example.test")

    assert len(sent) == 3


@pytest.mark.parametrize(
    ("candidate", "valid"),
    [
        ("ab", False),
        ("abc", True),
        ("a" * 20, True),
        ("a" * 21, False),
        ("has space", False),
        ("has-dash", False),
        ("under_score9", True),
    ],
)
def test_username_shape(candidate: str, valid: bool) -> None:
    assert usernames.is_valid(candidate) is valid


async def test_usernames_are_unique_case_insensitively(db: AsyncSession) -> None:
    await build_user(db, username="Cartographer")

    assert await usernames.is_available(db, "cartographer") is False
    assert await usernames.is_available(db, "CARTOGRAPHER") is False
    assert await usernames.is_available(db, "surveyor") is True


async def test_a_username_is_immutable_once_locked(db: AsyncSession) -> None:
    user = await build_user(db, username="early")
    user.username_locked_at = datetime.now(UTC) + timedelta(days=7)

    await usernames.rename(db, user, "renamed")
    assert user.username == "renamed"

    user.username_locked_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(usernames.UsernameLockedError):
        await usernames.rename(db, user, "toolate")


async def test_profile_of_an_unknown_username_is_none(db: AsyncSession) -> None:
    assert await accounts.profile(db, "nobody") is None


async def test_passport_counts_discoveries_by_country(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)
    user = await build_user(db, username="collector")
    from sqlalchemy import select

    from app.models import Place

    for name in ("Dildo", "Boring", "Truth or Consequences"):
        place = (await db.execute(select(Place).where(Place.name == name))).scalars().one()
        await build_discovery(db, place_id=place.id, user_id=user.id)

    passport = await accounts.passport(db, "collector")

    assert passport is not None
    assert passport.discoveries == 3
    assert passport.first_finds == 3
    assert passport.countries == {"CA": 1, "US": 2}


def test_the_module_exposes_exactly_four_public_functions() -> None:
    public = [
        name
        for name, value in vars(accounts).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["authenticate", "passport", "profile", "request_magic_link"]
