"""Accounts: sign-in, profiles and passports.

Token issue and expiry, session signing, username rules and stamp
aggregation all live behind these four functions.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from uuid import UUID

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Discovery, MagicLink, Place, User
from app.modules.accounts import delivery, streak, usernames

MAGIC_LINK_TTL: Final = timedelta(minutes=15)
MAGIC_LINKS_PER_HOUR: Final = 3
SESSION_TTL_SECONDS: Final = 60 * 60 * 24 * 30


class TooManyRequestsError(Exception):
    """Raised when an email asks for too many sign-in links in an hour."""


@dataclass(frozen=True, slots=True)
class Session:
    user_id: UUID
    username: str
    cookie: str


@dataclass(frozen=True, slots=True)
class PublicProfile:
    username: str
    joined_at: datetime
    discoveries: int


@dataclass(frozen=True, slots=True)
class Passport:
    username: str
    discoveries: int
    first_finds: int
    countries: dict[str, int]
    #: Share of each country's gazetteer places this user has found, 0..1.
    completion: dict[str, float]
    #: Consecutive days with a discovery or a vote.
    streak_days: int
    #: A live streak with nothing done today.
    streak_at_risk: bool


def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="toponomicon-session")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _session_for(user: User) -> Session:
    return Session(
        user_id=user.id,
        username=user.username,
        cookie=_signer().dumps(str(user.id)),
    )


def _user_id_from_cookie(token: str) -> UUID | None:
    try:
        raw = _signer().loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


async def _user_for_email(session: AsyncSession, email: str) -> User:
    existing = (await session.execute(select(User).where(User.email == email))).scalars().first()
    if existing is not None:
        return existing

    user = User(
        email=email,
        username=await usernames.suggest(session, email),
        username_locked_at=datetime.now(UTC) + timedelta(days=usernames.GRACE_DAYS),
    )
    session.add(user)
    await session.flush()
    return user


async def request_magic_link(session: AsyncSession, redis: Redis, email: str) -> None:
    """Issue a sign-in link. Rate limited per email; the IP is never stored."""
    normalized = email.casefold()

    key = f"magic-link:{normalized}"
    attempts = await redis.incr(key)
    if attempts == 1:
        await redis.expire(key, 3600)
    if attempts > MAGIC_LINKS_PER_HOUR:
        raise TooManyRequestsError(normalized)

    token = secrets.token_urlsafe(32)
    session.add(
        MagicLink(
            email=normalized,
            token_hash=_digest(token),
            expires_at=datetime.now(UTC) + MAGIC_LINK_TTL,
        )
    )
    await session.flush()
    await delivery.send_magic_link(email, token)


async def authenticate(session: AsyncSession, token: str) -> Session | None:
    """Turn a magic link or a session cookie into a session. None if neither."""
    user_id = _user_id_from_cookie(token)
    if user_id is not None:
        user = await session.get(User, user_id)
        return None if user is None else _session_for(user)

    link = (
        (await session.execute(select(MagicLink).where(MagicLink.token_hash == _digest(token))))
        .scalars()
        .first()
    )
    if link is None or link.used_at is not None or link.expires_at <= datetime.now(UTC):
        return None

    link.used_at = datetime.now(UTC)
    user = await _user_for_email(session, link.email)
    await session.flush()
    return _session_for(user)


async def profile(session: AsyncSession, username: str) -> PublicProfile | None:
    """The public view of an account, or None for an unknown username."""
    user = (
        (
            await session.execute(
                select(User).where(func.lower(User.username) == username.casefold())
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        return None

    found = await session.scalar(
        select(func.count()).select_from(Discovery).where(Discovery.user_id == user.id)
    )
    return PublicProfile(
        username=user.username,
        joined_at=user.created_at,
        discoveries=int(found or 0),
    )


async def _active_days(session: AsyncSession, user_id: UUID) -> set[date]:
    """Days this user did something that counts, in UTC."""
    rows = await session.execute(
        sql(
            "SELECT DISTINCT (created_at AT TIME ZONE 'UTC')::date AS day "
            "FROM discoveries WHERE user_id = :user_id "
            "UNION "
            "SELECT DISTINCT (created_at AT TIME ZONE 'UTC')::date "
            "FROM votes WHERE user_id = :user_id"
        ),
        {"user_id": user_id},
    )
    return {row[0] for row in rows}


async def passport(session: AsyncSession, username: str) -> Passport | None:
    """Stamps by country. Every discovery is a first find; the table enforces it."""
    user = (
        (
            await session.execute(
                select(User).where(func.lower(User.username) == username.casefold())
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        return None

    rows = await session.execute(
        select(Place.country_code, func.count())
        .join(Discovery, Discovery.place_id == Place.id)
        .where(Discovery.user_id == user.id)
        .group_by(Place.country_code)
    )
    countries = {code: int(count) for code, count in rows if code is not None}
    total = sum(countries.values())

    completion: dict[str, float] = {}
    if countries:
        available = await session.execute(
            select(Place.country_code, func.count())
            .where(Place.country_code.in_(countries))
            .group_by(Place.country_code)
        )
        for code, count in available:
            if code is not None and count:
                completion[code] = countries[code] / int(count)

    active = await _active_days(session, user.id)
    today = datetime.now(UTC).date()

    return Passport(
        username=user.username,
        discoveries=total,
        # Every discovery is a first find: one per place, enforced by the
        # unique constraint, so these two numbers cannot diverge.
        first_finds=total,
        countries=countries,
        completion=completion,
        streak_days=streak.length(active, today),
        streak_at_risk=streak.at_risk(active, today),
    )
