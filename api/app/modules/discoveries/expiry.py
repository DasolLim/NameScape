"""Releasing guest claims whose week has run out.

Internal to discoveries: the module's public interface is three functions, and
expiry is a scheduled chore rather than a capability callers reach for.

A release is a delete. No first-finder credit was ever awarded for a guest
claim, so there is nothing to withdraw, and the place returns to the state it
was in before - unclaimed, and claimable by anyone.
"""

from typing import Final

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

#: RETURNING rather than rowcount, so the count is the rows themselves and the
#: ids are there to log if a release ever needs explaining.
_RELEASE_SQL: Final = sql(
    "DELETE FROM discoveries "
    "WHERE claimant_type = 'guest' AND expires_at IS NOT NULL AND expires_at <= now() "
    "RETURNING place_id"
)


async def release_expired(session: AsyncSession) -> int:
    """Delete every guest claim past its deadline. Returns how many."""
    released = (await session.execute(_RELEASE_SQL)).scalars().all()
    return len(released)
