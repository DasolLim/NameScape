"""Discoveries: claim a place, list pins, list a user's finds.

Eligibility, moderation, first-finder uniqueness and the unique-constraint
race all live behind these three functions.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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

#: How long a guest claim stands before the place is released. Long enough to
#: come back to, short enough that the claim is visibly at stake.
GUEST_CLAIM_TTL: Final = timedelta(days=7)

#: What the globe calls a claim nobody has put a name to yet.
GUEST_FINDER: Final = "a guest"

#: Postgres unique_violation. Any other integrity error is a different bug.
_UNIQUE_VIOLATION: Final = "23505"


@dataclass(frozen=True, slots=True)
class UserClaimant:
    """A signed-in account. Its claim is permanent."""

    id: UUID


@dataclass(frozen=True, slots=True)
class GuestClaimant:
    """An unsigned visitor. One claim, and it expires."""

    id: UUID


Claimant = UserClaimant | GuestClaimant


class AlreadyClaimedError(Exception):
    """Raised when a place already has its one discovery."""


class NotEligibleError(Exception):
    """Raised when the game does not run at this place."""

    def __init__(self, reason: str | None) -> None:
        super().__init__(reason or "This place cannot be claimed.")
        self.reason = reason


class GuestLimitReachedError(Exception):
    """A guest session gets one claim. Signing up is what lifts the limit."""


class CaptionRejectedError(Exception):
    """Raised when the caption fails moderation. Carries no reason by design."""


class EtymologyRequiredError(Exception):
    """Raised when a Tier B place is claimed without saying what the name means."""

    def __init__(self, reason: str | None) -> None:
        super().__init__(reason or "Tell us what this name means before claiming it.")
        self.reason = reason


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
    #: Set only on a guest claim: when this place is released again.
    expires_at: datetime | None = None


_PINS_SQL: Final = """
    SELECT d.id, p.id AS place_id, p.name, COALESCE(u.username, :guest_finder) AS finder,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat
    FROM discoveries d
    JOIN places p ON p.id = d.place_id
    LEFT JOIN users u ON u.id = d.user_id
    WHERE ST_Intersects(
        p.centroid,
        ST_MakeEnvelope(:west, :south, :east, :north, 4326)::geography
    )
    ORDER BY p.population DESC, d.id
    LIMIT :limit
"""

#: Keyed on whichever column the claimant owns. A guest reading their own
#: claim is how the deadline survives a page reload, and how the interface
#: knows to explain the claim control rather than offer it again.
_FOR_CLAIMANT_SQL: Final = """
    SELECT d.id, p.id AS place_id, p.name, p.country_code, d.caption,
           d.created_at, d.expires_at
    FROM discoveries d
    JOIN places p ON p.id = d.place_id
    WHERE d.{column} = :claimant_id
    ORDER BY d.created_at DESC, d.id DESC
"""


async def claim(
    session: AsyncSession,
    place_id: int,
    claimant: Claimant,
    caption: str,
    etymology: str | None = None,
) -> Discovery:
    """Claim a place. Order matters: eligibility, then moderation, then insert.

    A guest claims on exactly the same terms as an account, bar two: they get
    one claim, and it expires. Nothing else is relaxed for them.
    """
    if not caption.strip():
        raise CaptionRejectedError
    if len(caption) > MAX_CAPTION_LENGTH:
        raise CaptionRejectedError

    if isinstance(claimant, GuestClaimant) and await _guest_has_claimed(session, claimant.id):
        raise GuestLimitReachedError

    verdict = await eligibility.check(
        session, place_id, claimant.id if isinstance(claimant, UserClaimant) else None
    )
    if verdict.status is eligibility.Eligibility.BLOCKED:
        raise NotEligibleError(verdict.reason)
    if verdict.status is eligibility.Eligibility.ETYMOLOGY_REQUIRED and not (
        etymology and etymology.strip()
    ):
        raise EtymologyRequiredError(verdict.reason)

    # Only now is it worth spending a classifier call.
    screened = await moderation.screen(
        session, caption, moderation.ScreenContext(place_id=place_id, kind="caption")
    )
    if screened.verdict is not moderation.Verdict.ACCEPT:
        raise CaptionRejectedError

    discovery = _row_for(claimant, place_id, caption)
    session.add(discovery)
    try:
        # The unique constraint on place_id is the real arbiter under a race.
        await session.flush()
    except IntegrityError as conflict:
        # Only a unique violation means somebody committed first. A forged
        # guest session or a place that vanished is a different fault and
        # must not be reported to the user as a race they lost.
        if getattr(conflict.orig, "sqlstate", None) != _UNIQUE_VIOLATION:
            raise
        raise AlreadyClaimedError(place_id) from conflict

    return discovery


#: Two ways a guest session can have spent its one claim: it still holds the
#: row, or the row was merged into an account, which clears the link back to
#: the session and leaves merged_into as the only remaining record of it.
_SPENT_SQL: Final = sql(
    "SELECT EXISTS (SELECT 1 FROM discoveries WHERE guest_session_id = :id) "
    "    OR EXISTS (SELECT 1 FROM guest_sessions "
    "               WHERE id = :id AND merged_into IS NOT NULL)"
)


async def _guest_has_claimed(session: AsyncSession, guest_session_id: UUID) -> bool:
    return bool(await session.scalar(_SPENT_SQL, {"id": guest_session_id}))


def _row_for(claimant: Claimant, place_id: int, caption: str) -> Discovery:
    """The CHECK constraint accepts exactly one of these two shapes."""
    if isinstance(claimant, GuestClaimant):
        return Discovery(
            place_id=place_id,
            caption=caption,
            claimant_type="guest",
            guest_session_id=claimant.id,
            expires_at=datetime.now(UTC) + GUEST_CLAIM_TTL,
        )
    return Discovery(place_id=place_id, caption=caption, claimant_type="user", user_id=claimant.id)


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
                "guest_finder": GUEST_FINDER,
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


async def for_user(session: AsyncSession, claimant: Claimant) -> list[UserDiscovery]:
    """A claimant's discoveries, newest first. Empty for a claimant with none."""
    column = "user_id" if isinstance(claimant, UserClaimant) else "guest_session_id"
    rows = (
        await session.execute(
            sql(_FOR_CLAIMANT_SQL.format(column=column)), {"claimant_id": claimant.id}
        )
    ).all()

    return [
        UserDiscovery(
            id=int(row[0]),
            place_id=int(row[1]),
            place_name=row[2],
            country_code=row[3],
            caption=row[4],
            created_at=row[5],
            expires_at=row[6],
        )
        for row in rows
    ]
