"""Approve drafted puzzles, one day at a time or in a reviewed run.

    uv run python scripts/approve_puzzles.py --list
    uv run python scripts/approve_puzzles.py --date 2026-09-01 --by dasol
    uv run python scripts/approve_puzzles.py --through 2026-09-30 --by dasol

Separate from generation on purpose: a person reads the clues before anyone
plays them. The one thing a drafted clue can get catastrophically wrong is
giving the answer away, and the deterministic check catches the obvious cases
while a reader catches the rest.

Approving is not the same as going live. The play path takes approved puzzles
for the current date, so approving a future date does nothing until that date
arrives.
"""

import argparse
import asyncio
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Place, Puzzle


async def show_drafts() -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(Puzzle, Place.name)
                .join(Place, Place.id == Puzzle.place_id)
                .where(Puzzle.status == "draft")
                .order_by(Puzzle.puzzle_date)
            )
        ).all()

    if not rows:
        print("no drafts")
        return

    for puzzle, name in rows:
        print(f"\n{puzzle.puzzle_date}  {name}  ({puzzle.generated_by})")
        for index, clue in enumerate(puzzle.clues, start=1):
            print(f"  {index}. {clue}")


async def approve(day: date | None, through: date | None, by: str) -> None:
    async with SessionLocal() as session:
        query = select(Puzzle).where(Puzzle.status == "draft")
        query = (
            query.where(Puzzle.puzzle_date == day)
            if day
            else query.where(Puzzle.puzzle_date <= through)
        )
        drafts = (await session.execute(query)).scalars().all()

        for puzzle in drafts:
            puzzle.status = "approved"
            puzzle.approved_by = by
        await session.commit()

    print(f"approved {len(drafts)} puzzles as {by}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print every draft and its clues")
    parser.add_argument("--date", default=None, help="approve one ISO date")
    parser.add_argument("--through", default=None, help="approve every draft up to this ISO date")
    parser.add_argument("--by", default=None, help="who approved it")
    parsed = parser.parse_args()

    if parsed.list or not (parsed.date or parsed.through):
        asyncio.run(show_drafts())
    elif not parsed.by:
        raise SystemExit("--by is required: an approval belongs to somebody")
    else:
        asyncio.run(
            approve(
                date.fromisoformat(parsed.date) if parsed.date else None,
                date.fromisoformat(parsed.through) if parsed.through else None,
                parsed.by,
            )
        )
