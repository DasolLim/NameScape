"""Username rules. Internal to the accounts module."""

import re
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

_SHAPE: Final = re.compile(r"[A-Za-z0-9_]{3,20}")
GRACE_DAYS: Final = 7


class UsernameLockedError(Exception):
    """Raised when a username is changed after its grace period."""


class UsernameUnavailableError(Exception):
    """Raised when a username is malformed or already taken."""


def is_valid(candidate: str) -> bool:
    return _SHAPE.fullmatch(candidate) is not None


async def is_available(session: AsyncSession, candidate: str) -> bool:
    taken = await session.execute(
        select(User.id).where(func.lower(User.username) == candidate.casefold())
    )
    return taken.first() is None


async def rename(session: AsyncSession, user: User, new_name: str) -> None:
    locked_at = user.username_locked_at
    if locked_at is not None and locked_at <= datetime.now(UTC):
        raise UsernameLockedError(f"{user.username} was locked at {locked_at.isoformat()}")
    if not is_valid(new_name):
        raise UsernameUnavailableError(new_name)
    if not await is_available(session, new_name):
        raise UsernameUnavailableError(new_name)

    user.username = new_name
    await session.flush()


async def suggest(session: AsyncSession, email: str) -> str:
    """A first username derived from the email, made unique."""
    base = re.sub(r"[^A-Za-z0-9_]", "", email.split("@")[0])[:20]
    if len(base) < 3:
        base = f"{base}finder"[:20]

    candidate = base
    suffix = 0
    while not await is_available(session, candidate):
        suffix += 1
        candidate = f"{base[:16]}{suffix}"
    return candidate
