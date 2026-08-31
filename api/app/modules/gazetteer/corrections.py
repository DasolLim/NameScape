"""Readers correcting a stored etymology.

Internal to the gazetteer: the module's public interface is three functions,
and a correction is a submission rather than a lookup.

Held for review, never applied on the spot. The entry a correction would
replace is often cited, and a correction is a claim about the world that the
system cannot check, so a person decides. Moderation runs first because this is
free text people write.
"""

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EtymologyCorrection, Place
from app.modules import moderation
from app.modules.moderation.normalize import normalize

MAX_LENGTH: Final = 500


class RejectedError(Exception):
    """Moderation refused it. Carries no reason, by the same rule as captions."""


class DuplicateError(Exception):
    """This person has already filed this claim about this place."""


class UnknownPlaceError(Exception):
    """No such place to correct."""


@dataclass(frozen=True, slots=True)
class Correction:
    id: int
    place_id: int
    status: str


async def submit(session: AsyncSession, place_id: int, user_id: UUID, text: str) -> Correction:
    """Record a correction for review."""
    trimmed = text.strip()
    if not trimmed or len(trimmed) > MAX_LENGTH:
        raise RejectedError

    if await session.get(Place, place_id) is None:
        raise UnknownPlaceError(place_id)

    screened = await moderation.screen(
        session, trimmed, moderation.ScreenContext(place_id=place_id, kind="caption")
    )
    if screened.verdict is not moderation.Verdict.ACCEPT:
        raise RejectedError

    correction = EtymologyCorrection(
        place_id=place_id,
        user_id=user_id,
        text=trimmed,
        normalized_text=normalize(trimmed),
        status="pending",
    )
    try:
        # A savepoint, so a duplicate leaves the caller's transaction usable.
        # A bare failed flush poisons the session, and the endpoint may still
        # have work to do after answering 409.
        async with session.begin_nested():
            session.add(correction)
            await session.flush()
    except IntegrityError as conflict:
        raise DuplicateError(place_id) from conflict

    return Correction(id=correction.id, place_id=place_id, status=correction.status)
