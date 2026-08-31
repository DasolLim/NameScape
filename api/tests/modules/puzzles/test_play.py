"""Playing the daily puzzle.

Three public functions and nothing else: the clue ladder, the geometry, the
banding, the streak and the share grid all sit behind them.

The share grid is the part that leaves the product, so it is the part that must
not leak. A grid that names the place is a spoiler pasted into a group chat.
"""

import inspect
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place, Puzzle, PuzzleAttempt, Streak
from app.modules import discoveries, puzzles
from app.modules.puzzles import geo, play
from tests.factories import build_guest_session, build_place, build_user

TODAY = date(2026, 9, 1)


class Spot(NamedTuple):
    name: str
    lon: float
    lat: float
    geonames_id: int


# The answer, and three places at known distances from it.
CARDIFF = Spot("Cardiff", -3.1791, 51.4816, 2_653_822)
BRISTOL = Spot("Bristol", -2.5879, 51.4545, 2_654_675)
BERLIN = Spot("Berlin", 13.4050, 52.5200, 2_950_159)
SYDNEY = Spot("Sydney", 151.2093, -33.8688, 2_147_714)


async def place_at(db: AsyncSession, spot: Spot) -> Place:
    return await build_place(
        db, tier=2, name=spot.name, lon=spot.lon, lat=spot.lat, geonames_id=spot.geonames_id
    )


async def a_puzzle(
    db: AsyncSession, *, day: date = TODAY, status: str = "approved", seq: int = 0
) -> tuple[Puzzle, Place]:
    """A puzzle on Cardiff's coordinates. `seq` varies the identity, because a
    place is the answer only once and a run of days needs a run of places."""
    place = await place_at(
        db,
        CARDIFF._replace(
            name=f"{CARDIFF.name}{'' if seq == 0 else f' {seq}'}",
            geonames_id=CARDIFF.geonames_id + seq,
        ),
    )
    puzzle = Puzzle(
        puzzle_date=day,
        place_id=place.id,
        clues=["A fort on a river.", "It is a populated place, a city.", "Europe", "Wales"],
        status=status,
        generated_by="fake/model-1",
    )
    db.add(puzzle)
    await db.flush()
    return puzzle, place


async def a_player(db: AsyncSession, *, username: str = "player") -> discoveries.Claimant:
    user = await build_user(db, username=username)
    return discoveries.UserClaimant(user.id)


async def test_today_is_the_same_puzzle_for_everybody(db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)

    first = await puzzles.today(db, on=TODAY)
    second = await puzzles.today(db, on=TODAY)

    assert first is not None
    assert first.id == puzzle.id == (second.id if second else 0)


async def test_a_day_with_no_approved_puzzle_has_no_puzzle(db: AsyncSession) -> None:
    """And emphatically not a random place: a puzzle nobody reviewed is worse
    than a day without one."""
    await a_puzzle(db, status="draft")
    await build_place(db, name="Somewhere Else", geonames_id=999_001, tier=1)

    assert await puzzles.today(db, on=TODAY) is None


async def test_a_puzzle_for_another_day_is_not_todays(db: AsyncSession) -> None:
    await a_puzzle(db, day=TODAY + timedelta(days=1))

    assert await puzzles.today(db, on=TODAY) is None


async def test_the_first_clue_is_there_before_any_guess(db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)

    state = await puzzles.state_for(db, puzzle.id, player)

    assert state.clues == ["A fort on a river."]
    assert state.guesses == []
    assert state.solved is False
    assert state.complete is False
    assert state.remaining == play.MAX_GUESSES


async def test_each_wrong_guess_reveals_exactly_one_more_clue(db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    wrong = await place_at(db, BERLIN)

    for expected in (2, 3, 4):
        await puzzles.guess(db, puzzle.id, player, wrong.id)
        state = await puzzles.state_for(db, puzzle.id, player)
        assert len(state.clues) == expected

    # The fourth wrong guess earns the pin, which is the place itself rather
    # than a sentence, so the prose clues stop at four.
    await puzzles.guess(db, puzzle.id, player, wrong.id)
    state = await puzzles.state_for(db, puzzle.id, player)
    assert len(state.clues) == 4
    assert state.pin is not None


async def test_a_guess_reports_distance_bearing_and_band(db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    bristol = await place_at(db, BRISTOL)

    result = await puzzles.guess(db, puzzle.id, player, bristol.id)

    # About 41km apart, so near. The arrow points from the guess towards the
    # answer, which is the direction the player should move next: Cardiff is
    # west of Bristol.
    assert result.distance_km == pytest.approx(41, abs=3)
    assert result.band is geo.Band.NEAR
    assert result.arrow == "⬅️"
    assert result.proximity > 99
    assert result.solved is False


async def test_a_correct_guess_ends_the_attempt_and_reveals_the_place(
    db: AsyncSession,
) -> None:
    puzzle, place = await a_puzzle(db)
    player = await a_player(db)

    result = await puzzles.guess(db, puzzle.id, player, place.id)

    assert result.solved is True
    assert result.band is geo.Band.CORRECT
    assert result.distance_km == 0
    assert result.answer is not None
    assert result.answer.name == "Cardiff"

    state = await puzzles.state_for(db, puzzle.id, player)
    assert state.solved is True
    assert state.complete is True
    assert state.answer is not None


async def test_the_answer_is_withheld_until_the_attempt_is_over(db: AsyncSession) -> None:
    """Otherwise the answer is one network tab away from anybody curious."""
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    wrong = await place_at(db, BERLIN)

    await puzzles.guess(db, puzzle.id, player, wrong.id)
    state = await puzzles.state_for(db, puzzle.id, player)

    assert state.answer is None
    assert state.pin is None


async def test_a_fifth_wrong_guess_ends_it_unsolved_and_shows_the_answer(
    db: AsyncSession,
) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    wrong = await place_at(db, SYDNEY)

    for _ in range(play.MAX_GUESSES):
        result = await puzzles.guess(db, puzzle.id, player, wrong.id)

    assert result.solved is False
    assert result.complete is True
    assert result.answer is not None

    state = await puzzles.state_for(db, puzzle.id, player)
    assert state.complete is True
    assert state.solved is False
    assert state.remaining == 0


async def test_guessing_after_the_attempt_is_over_is_refused(db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db)
    player = await a_player(db)
    await puzzles.guess(db, puzzle.id, player, place.id)

    with pytest.raises(play.AttemptCompleteError):
        await puzzles.guess(db, puzzle.id, player, place.id)


async def test_guessing_a_place_that_is_not_in_the_gazetteer_is_refused(
    db: AsyncSession,
) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)

    with pytest.raises(play.UnknownPlaceError):
        await puzzles.guess(db, puzzle.id, player, 999_999)


async def test_a_guest_can_play_and_their_attempt_is_their_own(db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db)
    mine = discoveries.GuestClaimant((await build_guest_session(db)).id)
    theirs = discoveries.GuestClaimant((await build_guest_session(db)).id)

    await puzzles.guess(db, puzzle.id, mine, place.id)

    assert (await puzzles.state_for(db, puzzle.id, mine)).solved is True
    assert (await puzzles.state_for(db, puzzle.id, theirs)).solved is False

    attempt = (
        (await db.execute(select(PuzzleAttempt).where(PuzzleAttempt.solved.is_(True))))
        .scalars()
        .one()
    )
    assert attempt.guest_session_id == mine.id
    assert attempt.user_id is None


async def test_a_streak_grows_on_consecutive_days(db: AsyncSession) -> None:
    player = await a_player(db)
    for offset in range(3):
        day = TODAY + timedelta(days=offset)
        puzzle, place = await a_puzzle(db, day=day, seq=offset)
        await puzzles.guess(db, puzzle.id, player, place.id, on=day)

    streak = (await db.execute(select(Streak))).scalars().one()
    assert streak.current == 3
    assert streak.longest == 3
    assert streak.last_played_on == TODAY + timedelta(days=2)


async def test_a_missed_day_resets_the_streak_but_not_the_record(
    db: AsyncSession,
) -> None:
    player = await a_player(db)
    first, place = await a_puzzle(db, day=TODAY)
    await puzzles.guess(db, first.id, player, place.id, on=TODAY)

    gap = TODAY + timedelta(days=3)
    later, other = await a_puzzle(db, day=gap, seq=1)
    await puzzles.guess(db, later.id, player, other.id, on=gap)

    streak = (await db.execute(select(Streak))).scalars().one()
    assert streak.current == 1
    assert streak.longest == 1
    assert streak.last_played_on == gap


async def test_the_same_day_solved_twice_does_not_double_the_streak(
    db: AsyncSession,
) -> None:
    """It cannot happen through guess(), but a streak that can be inflated by a
    retry is a streak worth inflating."""
    player = await a_player(db)
    puzzle, place = await a_puzzle(db)
    await puzzles.guess(db, puzzle.id, player, place.id, on=TODAY)

    await play.record_solve(db, player, TODAY)

    streak = (await db.execute(select(Streak))).scalars().one()
    assert streak.current == 1


async def test_a_guest_has_no_streak_to_keep(db: AsyncSession) -> None:
    """Streaks are the reason to make an account, so they belong to accounts."""
    puzzle, place = await a_puzzle(db)
    guest = discoveries.GuestClaimant((await build_guest_session(db)).id)

    await puzzles.guess(db, puzzle.id, guest, place.id, on=TODAY)

    assert (await db.execute(select(Streak))).scalars().all() == []


async def test_the_share_grid_gives_nothing_away(db: AsyncSession) -> None:
    """The acceptance criterion. This text is pasted into group chats."""
    puzzle, place = await a_puzzle(db)
    player = await a_player(db)
    berlin = await place_at(db, BERLIN)
    bristol = await place_at(db, BRISTOL)

    await puzzles.guess(db, puzzle.id, player, berlin.id)
    await puzzles.guess(db, puzzle.id, player, bristol.id)
    await puzzles.guess(db, puzzle.id, player, place.id, on=TODAY)

    state = await puzzles.state_for(db, puzzle.id, player)
    grid = state.share_grid

    assert "Cardiff" not in grid
    assert "Wales" not in grid
    assert "Berlin" not in grid
    assert "Bristol" not in grid
    # Nor a coordinate, which would be a spoiler in a different notation.
    assert "51.4" not in grid
    assert "-3.1" not in grid

    # It does say how it went: the number, the score, and the markers.
    assert "3/5" in grid
    assert grid.count("🟩") == 1
    assert "toponomicon" in grid.casefold()


async def test_an_unsolved_grid_says_so_rather_than_pretending(
    db: AsyncSession,
) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    wrong = await place_at(db, SYDNEY)

    for _ in range(play.MAX_GUESSES):
        await puzzles.guess(db, puzzle.id, player, wrong.id)

    grid = (await puzzles.state_for(db, puzzle.id, player)).share_grid

    assert "X/5" in grid
    assert "🟩" not in grid


async def test_the_grid_carries_the_streak_when_there_is_one(db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db)
    player = await a_player(db)
    await puzzles.guess(db, puzzle.id, player, place.id, on=TODAY)

    grid = (await puzzles.state_for(db, puzzle.id, player)).share_grid

    assert "🔥1" in grid


async def test_an_unfinished_attempt_has_no_grid_to_share(db: AsyncSession) -> None:
    puzzle, _ = await a_puzzle(db)
    player = await a_player(db)
    berlin = await place_at(db, BERLIN)
    await puzzles.guess(db, puzzle.id, player, berlin.id)

    assert (await puzzles.state_for(db, puzzle.id, player)).share_grid == ""


async def test_the_puzzle_number_counts_from_the_first_day(db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db, day=play.EPOCH + timedelta(days=141))
    player = await a_player(db)
    await puzzles.guess(db, puzzle.id, player, place.id, on=play.EPOCH + timedelta(days=141))

    grid = (await puzzles.state_for(db, puzzle.id, player)).share_grid

    assert "#142" in grid


async def test_a_completed_attempt_records_when_it_ended(db: AsyncSession) -> None:
    puzzle, place = await a_puzzle(db)
    player = await a_player(db)

    await puzzles.guess(db, puzzle.id, player, place.id)

    attempt = (await db.execute(select(PuzzleAttempt))).scalars().one()
    assert attempt.completed_at is not None
    assert attempt.completed_at <= datetime.now(UTC)


def test_the_module_exposes_exactly_three_public_functions() -> None:
    public = [
        name
        for name, value in vars(puzzles).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["guess", "state_for", "today"]
