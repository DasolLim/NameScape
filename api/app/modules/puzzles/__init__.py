"""Puzzles: today(), guess(), state_for().

One mystery place per day, identical for every player worldwide. Five guesses,
one more clue per wrong one.

Behind these three functions: the clue ladder, the distance and bearing
arithmetic, the proximity bands, the streak, and the share grid. Generation is
separate and offline, in `generation`, because no model may be called while a
player waits.
"""

from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Puzzle
from app.modules.discoveries import Claimant
from app.modules.puzzles import play
from app.modules.puzzles.play import (
    Answer,
    AttemptCompleteError,
    AttemptState,
    Guess,
    GuessResult,
    NoPuzzleError,
    UnknownPlaceError,
)

__all__ = [
    "Answer",
    "AttemptCompleteError",
    "AttemptState",
    "Guess",
    "GuessResult",
    "NoPuzzleError",
    "UnknownPlaceError",
    "guess",
    "state_for",
    "today",
]


async def today(session: AsyncSession, on: date | None = None) -> Puzzle | None:
    """The approved puzzle for a date, the same one for every caller.

    None when no approved puzzle exists for that date. Never a random place: a
    puzzle nobody reviewed is worse than a day without one.
    """
    return await play.current(session, on or datetime.now(UTC).date())


async def guess(
    session: AsyncSession,
    puzzle_id: int,
    player: Claimant,
    place_id: int,
    on: date | None = None,
) -> GuessResult:
    """Record one guess and say how close it came."""
    return await play.make_guess(session, puzzle_id, player, place_id, on)


async def state_for(session: AsyncSession, puzzle_id: int, player: Claimant) -> AttemptState:
    """What this player has earned so far, and nothing more."""
    return await play.state(session, puzzle_id, player)
