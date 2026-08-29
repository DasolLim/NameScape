"""Discoveries: claim a place, list pins, list a user's finds.

Eligibility, moderation, first-finder uniqueness and the unique-constraint
race all live behind these three functions.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import text as sql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Discovery
from app.modules import eligibility, moderation

#: The globe cannot draw more than this without dropping frames on mobile.
MAX_FEATURES: Final = 500
MAX_CAPTION_LENGTH: Final = 140


class AlreadyClaimedError(Exception):
    """Raised when a place already has its one discovery."""


class NotEligibleError(Exception):
    """Raised when the game does not run at this place."""

    def __init__(self, reason: str | None) -> None:
        super().__init__(reason or "This place cannot be claimed.")
        self.reason = reason


class CaptionRejectedError(Exception):
    """Raised when the caption fails moderation. Carries no reason by design."""


@dataclass(frozen=True, slots=True)
class BBox:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True, slots=True)
class DiscoveryPin:
    id: int
    place_id: int
    place_name: str
    lon: float
    lat: float
    finder: str


@dataclass(frozen=True, slots=True)
class UserDiscovery:
    id: int
    place_id: int
    place_name: str
    country_code: str | None
    caption: str
    created_at: datetime


_PINS_SQL: Final = """
    SELECT d.id, p.id AS place_id, p.name, u.username,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat
    FROM discoveries d
    JOIN places p ON p.id = d.place_id
    JOIN users u ON u.id = d.user_id
    WHERE ST_Intersects(
        p.centroid,
        ST_MakeEnvelope(:west, :south, :east, :north, 4326)::geography
    )
    ORDER BY p.population DESC, d.id
    LIMIT :limit
"""

_FOR_USER_SQL: Final = """
    SELECT d.id, p.id AS place_id, p.name, p.country_code, d.caption, d.created_at
    FROM discoveries d
    JOIN places p ON p.id = d.place_id
    WHERE d.user_id = :user_id
    ORDER BY d.created_at DESC, d.id DESC
"""


async def claim(session: AsyncSession, place_id: int, user_id: UUID, caption: str) -> Discovery:
    """Claim a place. Order matters: eligibility, then moderation, then insert."""
    if not caption.strip():
        raise CaptionRejectedError
    if len(caption) > MAX_CAPTION_LENGTH:
        raise CaptionRejectedError

    verdict = await eligibility.check(session, place_id, user_id)
    if verdict.status is eligibility.Eligibility.BLOCKED:
        raise NotEligibleError(verdict.reason)

    # Only now is it worth spending a classifier call.
    screened = await moderation.screen(
        session, caption, moderation.ScreenContext(place_id=place_id, kind="caption")
    )
    if screened.verdict is not moderation.Verdict.ACCEPT:
        raise CaptionRejectedError

    discovery = Discovery(place_id=place_id, user_id=user_id, caption=caption)
    session.add(discovery)
    try:
        # The unique constraint on place_id is the real arbiter under a race.
        await session.flush()
    except IntegrityError as conflict:
        raise AlreadyClaimedError(place_id) from conflict

    return discovery


async def list_in_bounds(session: AsyncSession, bbox: BBox, zoom: int) -> list[DiscoveryPin]:
    """Discovery pins inside a bounding box, capped for the renderer."""
    rows = (
        await session.execute(
            sql(_PINS_SQL),
            {
                "west": bbox.west,
                "south": bbox.south,
                "east": bbox.east,
                "north": bbox.north,
                "limit": MAX_FEATURES,
            },
        )
    ).all()

    return [
        DiscoveryPin(
            id=int(row[0]),
            place_id=int(row[1]),
            place_name=row[2],
            finder=row[3],
            lon=float(row[4]),
            lat=float(row[5]),
        )
        for row in rows
    ]


async def for_user(session: AsyncSession, user_id: UUID) -> list[UserDiscovery]:
    """A user's discoveries, newest first."""
    rows = (await session.execute(sql(_FOR_USER_SQL), {"user_id": user_id})).all()

    return [
        UserDiscovery(
            id=int(row[0]),
            place_id=int(row[1]),
            place_name=row[2],
            country_code=row[3],
            caption=row[4],
            created_at=row[5],
        )
        for row in rows
    ]
