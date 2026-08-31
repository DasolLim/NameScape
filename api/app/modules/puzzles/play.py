"""Playing the daily puzzle. Internal; three functions are exported.

Everything interesting is hidden here: the clue ladder, the geometry, the
banding, the streak arithmetic and the share grid. A caller says who is playing
and what they guessed.

Two rules the whole surface rests on:

Only an approved puzzle is playable. A day with no approved puzzle simply has
no puzzle, and never falls back to a random place: a puzzle nobody reviewed is
worse than a day without one.

The answer is withheld until the attempt is over. Sending it early would put
the answer one network tab away from anybody curious.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place, Puzzle, PuzzleAttempt, Streak
from app.modules.discoveries import Claimant, UserClaimant
from app.modules.puzzles import geo

#: Five guesses, four prose clues, and the fifth reveal is the pin.
MAX_GUESSES: Final = 5

#: Day one. The puzzle number in the share grid counts from here, so it has to
#: be a constant: deriving it from the first row in the table would renumber
#: every grid anybody had already posted. Set this to the real first puzzle
#: date before launch.
EPOCH: Final = date(2026, 9, 1)

_APP_URL: Final = "toponomicon.app"


class AttemptCompleteError(Exception):
    """The player has already finished this puzzle."""


class UnknownPlaceError(Exception):
    """A guess at something that is not in the gazetteer."""


class NoPuzzleError(Exception):
    """No approved puzzle with that id."""


@dataclass(frozen=True, slots=True)
class Answer:
    """The place, revealed only once the attempt is over."""

    place_id: int
    name: str
    country_code: str | None
    lon: float
    lat: float
    claimed_by: str | None


@dataclass(frozen=True, slots=True)
class Guess:
    place_id: int
    name: str
    distance_km: float
    bearing: float
    band: geo.Band
    proximity: int

    @property
    def arrow(self) -> str:
        return geo.arrow(self.bearing)


@dataclass(frozen=True, slots=True)
class GuessResult:
    """What one guess earned."""

    distance_km: float
    bearing: float
    band: geo.Band
    proximity: int
    solved: bool
    complete: bool
    #: Present only once the attempt is over.
    answer: Answer | None

    @property
    def arrow(self) -> str:
        return geo.arrow(self.bearing)


@dataclass(frozen=True, slots=True)
class AttemptState:
    """Everything a player may see about their own attempt."""

    puzzle_id: int
    puzzle_number: int
    clues: list[str]
    guesses: list[Guess] = field(default_factory=list)
    solved: bool = False
    complete: bool = False
    remaining: int = MAX_GUESSES
    #: The pin clue, earned by a fourth wrong guess.
    pin: tuple[float, float] | None = None
    answer: Answer | None = None
    #: Empty until the attempt is over: there is nothing to boast about yet.
    share_grid: str = ""
    streak: int = 0


def puzzle_number(day: date) -> int:
    """Which puzzle this is, counting from the epoch.

    Never below one. A puzzle dated before the epoch is a development or
    seeding artefact, and "#0" in a grid posted to a group chat is the kind of
    bug people screenshot.
    """
    return max(1, (day - EPOCH).days + 1)


async def current(session: AsyncSession, on: date) -> Puzzle | None:
    """The approved puzzle for a date, or None. Never a fallback."""
    return (
        (
            await session.execute(
                select(Puzzle).where(
                    Puzzle.puzzle_date == on,
                    Puzzle.status.in_(("approved", "live")),
                )
            )
        )
        .scalars()
        .first()
    )


async def _coordinates(session: AsyncSession, place_id: int) -> tuple[float, float] | None:
    row = (
        await session.execute(
            sql(
                "SELECT ST_Y(centroid::geometry), ST_X(centroid::geometry) "
                "FROM places WHERE id = :id"
            ),
            {"id": place_id},
        )
    ).first()
    return (float(row[0]), float(row[1])) if row else None


async def _answer(session: AsyncSession, place_id: int) -> Answer:
    row = (
        await session.execute(
            sql(
                "SELECT p.name, p.country_code, ST_X(p.centroid::geometry), "
                "       ST_Y(p.centroid::geometry), u.username "
                "FROM places p "
                "LEFT JOIN discoveries d ON d.place_id = p.id "
                "LEFT JOIN users u ON u.id = d.user_id "
                "WHERE p.id = :id"
            ),
            {"id": place_id},
        )
    ).one()
    return Answer(
        place_id=place_id,
        name=row[0],
        country_code=row[1],
        lon=float(row[2]),
        lat=float(row[3]),
        claimed_by=row[4],
    )


async def _attempt(session: AsyncSession, puzzle_id: int, player: Claimant) -> PuzzleAttempt | None:
    column = (
        PuzzleAttempt.user_id
        if isinstance(player, UserClaimant)
        else PuzzleAttempt.guest_session_id
    )
    return (
        (
            await session.execute(
                select(PuzzleAttempt).where(
                    PuzzleAttempt.puzzle_id == puzzle_id, column == player.id
                )
            )
        )
        .scalars()
        .first()
    )


def _new_attempt(puzzle_id: int, player: Claimant) -> PuzzleAttempt:
    if isinstance(player, UserClaimant):
        return PuzzleAttempt(puzzle_id=puzzle_id, user_id=player.id, guesses=[])
    return PuzzleAttempt(puzzle_id=puzzle_id, guest_session_id=player.id, guesses=[])


async def record_solve(session: AsyncSession, player: Claimant, on: date) -> int:
    """Extend the player's streak. Returns its new length.

    Guests keep no streak: a streak is the strongest reason to make an account,
    so it is one of the things an account is for.

    Idempotent for a given day. Solving twice cannot happen through guess(),
    but a streak that a retry can inflate is a streak worth inflating.
    """
    if not isinstance(player, UserClaimant):
        return 0

    streak = await session.get(Streak, player.id)
    if streak is None:
        streak = Streak(user_id=player.id, current=0, longest=0)
        session.add(streak)

    if streak.last_played_on == on:
        return streak.current

    consecutive = streak.last_played_on == on - timedelta(days=1)
    streak.current = streak.current + 1 if consecutive else 1
    streak.longest = max(streak.longest, streak.current)
    streak.last_played_on = on
    await session.flush()
    return streak.current


async def _streak_length(session: AsyncSession, player: Claimant) -> int:
    if not isinstance(player, UserClaimant):
        return 0
    streak = await session.get(Streak, player.id)
    return streak.current if streak else 0


def share_grid(state_number: int, guesses: list[Guess], solved: bool, streak: int) -> str:
    """The postable summary.

    Everything identifying is left out by construction rather than by
    redaction: the grid is built from band markers and bearings, and the name,
    the country and the coordinates are simply never among the ingredients.
    """
    score = f"{len(guesses)}/{MAX_GUESSES}" if solved else f"X/{MAX_GUESSES}"
    header = f"Toponomicon #{state_number} · {score}"
    if streak > 0:
        header += f" · 🔥{streak}"

    rows = "  ".join(
        guess.band.marker if guess.band is geo.Band.CORRECT else f"{guess.band.marker}{guess.arrow}"
        for guess in guesses
    )
    return f"{header}\n{rows}\n\n{_APP_URL}"


def _guess_from(entry: object) -> Guess | None:
    """One stored guess, or None if the row is not the shape we wrote."""
    if not isinstance(entry, dict):
        return None
    place_id = entry.get("place_id")
    distance = entry.get("distance_km")
    bearing = entry.get("bearing")
    if not isinstance(place_id, int):
        return None
    if not isinstance(distance, int | float) or not isinstance(bearing, int | float):
        return None

    name = entry.get("name")
    return Guess(
        place_id=place_id,
        name=name if isinstance(name, str) else "",
        distance_km=float(distance),
        bearing=float(bearing),
        band=geo.band(float(distance)),
        proximity=geo.proximity(float(distance)),
    )


def _guesses_from(attempt: PuzzleAttempt) -> list[Guess]:
    stored = attempt.guesses if isinstance(attempt.guesses, list) else json.loads(attempt.guesses)
    return [guess for guess in (_guess_from(entry) for entry in stored) if guess is not None]


async def state(session: AsyncSession, puzzle_id: int, player: Claimant) -> AttemptState:
    """What this player may see. Clues earned, guesses made, nothing further."""
    puzzle = await session.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise NoPuzzleError(puzzle_id)

    attempt = await _attempt(session, puzzle_id, player)
    guesses = _guesses_from(attempt) if attempt else []
    solved = bool(attempt and attempt.solved)
    used = len(guesses)
    complete = solved or used >= MAX_GUESSES

    # One clue to start, one more per wrong guess, and the fourth wrong guess
    # earns the pin instead of a fifth sentence.
    wrong = used - (1 if solved else 0)
    clues = list(puzzle.clues[: min(1 + wrong, len(puzzle.clues))])
    pin = None
    if wrong >= len(puzzle.clues) or complete:
        pin = await _coordinates(session, puzzle.place_id)

    answer = await _answer(session, puzzle.place_id) if complete else None
    streak = await _streak_length(session, player) if complete else 0
    number = puzzle_number(puzzle.puzzle_date)

    return AttemptState(
        puzzle_id=puzzle_id,
        puzzle_number=number,
        clues=clues,
        guesses=guesses,
        solved=solved,
        complete=complete,
        remaining=max(0, MAX_GUESSES - used),
        pin=pin if complete or wrong >= len(puzzle.clues) else None,
        answer=answer,
        share_grid=share_grid(number, guesses, solved, streak) if complete else "",
        streak=streak,
    )


async def make_guess(
    session: AsyncSession,
    puzzle_id: int,
    player: Claimant,
    place_id: int,
    on: date | None = None,
) -> GuessResult:
    """Record one guess and say how close it came."""
    puzzle = await session.get(Puzzle, puzzle_id)
    if puzzle is None:
        raise NoPuzzleError(puzzle_id)

    attempt = await _attempt(session, puzzle_id, player)
    if attempt is None:
        attempt = _new_attempt(puzzle_id, player)
        session.add(attempt)
        await session.flush()

    if attempt.solved or attempt.guess_count >= MAX_GUESSES:
        raise AttemptCompleteError(puzzle_id)

    guessed = await _coordinates(session, place_id)
    if guessed is None:
        raise UnknownPlaceError(place_id)
    target = await _coordinates(session, puzzle.place_id)
    if target is None:
        raise UnknownPlaceError(puzzle.place_id)

    correct = place_id == puzzle.place_id
    distance = 0.0 if correct else geo.distance_km(guessed, target)
    bearing = 0.0 if correct else geo.bearing_degrees(guessed, target)
    guessed_place = await session.get(Place, place_id)

    # Reassigned rather than appended to: JSONB columns do not track in-place
    # mutation, so a list that is appended to is not saved.
    attempt.guesses = [
        *(attempt.guesses or []),
        {
            "place_id": place_id,
            "name": guessed_place.name if guessed_place else "",
            "distance_km": round(distance, 3),
            "bearing": round(bearing, 3),
        },
    ]
    attempt.guess_count = len(attempt.guesses)
    attempt.solved = correct
    complete = correct or attempt.guess_count >= MAX_GUESSES
    if complete:
        attempt.completed_at = datetime.now(UTC)
    await session.flush()

    if correct:
        await record_solve(session, player, on or puzzle.puzzle_date)

    return GuessResult(
        distance_km=distance,
        bearing=bearing,
        band=geo.band(distance),
        proximity=geo.proximity(distance),
        solved=correct,
        complete=complete,
        answer=await _answer(session, puzzle.place_id) if complete else None,
    )
