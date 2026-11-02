"""The daily puzzle and its archive."""

from datetime import date

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.modules import discoveries, puzzles
from app.modules.accounts import guests
from app.modules.puzzles import play
from app.routes.deps import (
    MAX_BIGINT,
    WRITE_ERRORS,
    GuestCookie,
    PlaceId,
    SessionCookie,
    SessionDep,
    errors,
    existing_claimant,
    set_guest_cookie,
    signed_in_user,
)

router = APIRouter()


class PuzzleGuessResponse(BaseModel):
    place_id: int
    name: str
    distance_km: float
    bearing: float
    #: One of eight, so the player is told which way to go next.
    arrow: str
    band: str
    proximity: int


class PuzzlePinResponse(BaseModel):
    lat: float
    lon: float


class PuzzleAnswerResponse(BaseModel):
    place_id: int
    name: str
    country_code: str | None
    lat: float
    lon: float
    claimed_by: str | None


class PuzzleStateResponse(BaseModel):
    puzzle_id: int
    number: int
    clues: list[str]
    guesses: list[PuzzleGuessResponse]
    solved: bool
    complete: bool
    remaining: int
    #: The last clue, earned by a fourth wrong guess. Drawn on the globe.
    pin: PuzzlePinResponse | None
    #: Withheld until the attempt is over.
    answer: PuzzleAnswerResponse | None
    share_grid: str
    streak: int


class ArchiveEntry(BaseModel):
    puzzle_id: int
    number: int
    date: date
    solved: bool
    guesses: int


class ArchiveResponse(BaseModel):
    puzzles: list[ArchiveEntry]


class GuessRequest(BaseModel):
    place_id: int = Field(ge=1, le=MAX_BIGINT)


def _state_response(state: puzzles.AttemptState) -> PuzzleStateResponse:
    answer = state.answer
    return PuzzleStateResponse(
        puzzle_id=state.puzzle_id,
        number=state.puzzle_number,
        clues=state.clues,
        guesses=[
            PuzzleGuessResponse(
                place_id=guess.place_id,
                name=guess.name,
                distance_km=round(guess.distance_km, 1),
                bearing=round(guess.bearing, 1),
                arrow=guess.arrow,
                band=guess.band.name.casefold(),
                proximity=guess.proximity,
            )
            for guess in state.guesses
        ],
        solved=state.solved,
        complete=state.complete,
        remaining=state.remaining,
        pin=PuzzlePinResponse(lat=state.pin[0], lon=state.pin[1]) if state.pin else None,
        answer=(
            PuzzleAnswerResponse(
                place_id=answer.place_id,
                name=answer.name,
                country_code=answer.country_code,
                lat=answer.lat,
                lon=answer.lon,
                claimed_by=answer.claimed_by,
            )
            if answer
            else None
        ),
        share_grid=state.share_grid,
        streak=state.streak,
    )


@router.get("/api/puzzle")
async def read_puzzle(
    session: SessionDep,
    namescape_session: SessionCookie = None,
    namescape_guest: GuestCookie = None,
) -> PuzzleStateResponse | None:
    """Today's puzzle and this player's progress. Null on a day without one."""
    puzzle = await puzzles.today(session)
    if puzzle is None:
        return None

    player = await existing_claimant(session, namescape_session, namescape_guest)
    if player is None:
        # Nobody to look up, so nothing has been earned: the opening state.
        return PuzzleStateResponse(
            puzzle_id=puzzle.id,
            number=play.puzzle_number(puzzle.puzzle_date),
            clues=list(puzzle.clues[:1]),
            guesses=[],
            solved=False,
            complete=False,
            remaining=play.MAX_GUESSES,
            pin=None,
            answer=None,
            share_grid="",
            streak=0,
        )

    return _state_response(await puzzles.state_for(session, puzzle.id, player))


@router.post("/api/puzzle/{puzzle_id}/guess", responses=errors(404, 409, *WRITE_ERRORS))
async def guess_puzzle(
    puzzle_id: PlaceId,
    body: GuessRequest,
    response: Response,
    session: SessionDep,
    namescape_session: SessionCookie = None,
    namescape_guest: GuestCookie = None,
) -> PuzzleStateResponse:
    """Guess, and hear how close it came. No account needed to play."""
    user = await signed_in_user(session, namescape_session)
    guest: guests.Guest | None = None
    if user is not None:
        player: discoveries.Claimant = discoveries.UserClaimant(user.id)
    else:
        # Guessing is the first moment there is anything to remember.
        guest = await guests.resolve(session, namescape_guest)
        player = discoveries.GuestClaimant(guest.id)

    try:
        await puzzles.guess(session, puzzle_id, player, body.place_id)
    except puzzles.NoPuzzleError:
        raise HTTPException(status_code=404, detail="No such puzzle") from None
    except puzzles.UnknownPlaceError:
        raise HTTPException(status_code=404, detail="No such place") from None
    except puzzles.AttemptCompleteError:
        raise HTTPException(status_code=409, detail="You have finished today's puzzle") from None

    state = await puzzles.state_for(session, puzzle_id, player)
    await session.commit()

    if guest is not None:
        set_guest_cookie(response, guest)
    return _state_response(state)


_ARCHIVE = text(
    "SELECT z.id, z.puzzle_date, "
    "       COALESCE(a.solved, false), COALESCE(a.guess_count, 0) "
    "FROM puzzles z "
    "LEFT JOIN puzzle_attempts a "
    "  ON a.puzzle_id = z.id AND a.user_id = :user_id "
    "WHERE z.status = 'archived' "
    "ORDER BY z.puzzle_date DESC LIMIT 90"
)


@router.get("/api/puzzle/archive", responses=errors(401))
async def read_puzzle_archive(
    session: SessionDep, namescape_session: SessionCookie = None
) -> ArchiveResponse:
    """Puzzles that have been and gone, and how they went.

    Account-gated, per Addendum A. No answers: it is for replaying, not for
    reading ahead. The refusal says what an account is for here rather than
    the generic "sign in", because the archive is a reason to have one.
    """
    user = await signed_in_user(session, namescape_session)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Past puzzles are kept with your account. Create one to play them.",
        )

    rows = (await session.execute(_ARCHIVE, {"user_id": user.id})).all()
    return ArchiveResponse(
        puzzles=[
            ArchiveEntry(
                puzzle_id=int(puzzle_id),
                number=play.puzzle_number(puzzle_date),
                date=puzzle_date,
                solved=bool(solved),
                guesses=int(guesses),
            )
            for puzzle_id, puzzle_date, solved, guesses in rows
        ]
    )
