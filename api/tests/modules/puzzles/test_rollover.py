"""The daily handover: today's puzzle goes live, yesterday's is archived.

Approving a puzzle months ahead is a person saying it is fit to play. Going
live is the calendar saying it is today's. Keeping those separate is what lets
ninety days of approved puzzles sit waiting without any of them being playable.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Puzzle
from app.modules.puzzles import rollover
from tests.factories import build_place

TODAY = date(2026, 9, 1)


async def a_puzzle(db: AsyncSession, day: date, status: str, seq: int) -> Puzzle:
    place = await build_place(db, name=f"Place {seq}", geonames_id=800_000 + seq, tier=2)
    puzzle = Puzzle(
        puzzle_date=day,
        place_id=place.id,
        clues=["A clue."],
        status=status,
        generated_by="fake/model-1",
    )
    db.add(puzzle)
    await db.flush()
    return puzzle


async def test_todays_approved_puzzle_goes_live(db: AsyncSession) -> None:
    puzzle = await a_puzzle(db, TODAY, "approved", 1)

    changed = await rollover.roll_over(db, on=TODAY)

    assert changed == 1
    assert puzzle.status == "live"


async def test_yesterdays_live_puzzle_is_archived(db: AsyncSession) -> None:
    puzzle = await a_puzzle(db, TODAY - timedelta(days=1), "live", 2)

    await rollover.roll_over(db, on=TODAY)

    assert puzzle.status == "archived"


async def test_a_future_puzzle_is_left_alone_however_approved_it_is(
    db: AsyncSession,
) -> None:
    """Ninety days of approved puzzles have to be able to sit and wait."""
    puzzle = await a_puzzle(db, TODAY + timedelta(days=30), "approved", 3)

    await rollover.roll_over(db, on=TODAY)

    assert puzzle.status == "approved"


async def test_a_draft_never_goes_live_no_matter_the_date(db: AsyncSession) -> None:
    """The one thing this job must not do: promote something nobody read."""
    puzzle = await a_puzzle(db, TODAY, "draft", 4)

    await rollover.roll_over(db, on=TODAY)

    assert puzzle.status == "draft"


async def test_a_second_run_changes_nothing(db: AsyncSession) -> None:
    await a_puzzle(db, TODAY, "approved", 5)
    await rollover.roll_over(db, on=TODAY)

    assert await rollover.roll_over(db, on=TODAY) == 0


async def test_a_missed_day_still_archives_and_promotes(db: AsyncSession) -> None:
    """A worker that was down for a week must not leave last Tuesday live."""
    stale = await a_puzzle(db, TODAY - timedelta(days=7), "live", 6)
    current = await a_puzzle(db, TODAY, "approved", 7)

    await rollover.roll_over(db, on=TODAY)

    assert stale.status == "archived"
    assert current.status == "live"
    live = (await db.execute(select(Puzzle).where(Puzzle.status == "live"))).scalars().all()
    assert [puzzle.id for puzzle in live] == [current.id]
