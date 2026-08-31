"""The daily handover. Internal.

Approval and going live are deliberately different things. A person approving a
puzzle months ahead is saying it is fit to play; the calendar saying it is today
is what makes it playable. Keeping them apart is what lets ninety days of
approved puzzles sit waiting without any of them being live.

Written so a worker that was down for a week catches up rather than leaving
last Tuesday's puzzle live.
"""

import logging
from datetime import UTC, date, datetime
from typing import Final

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Puzzle

logger = logging.getLogger(__name__)

#: Synchronised, so a Puzzle already loaded in this session is not left
#: claiming a status the database no longer agrees with.
_SYNC: Final = {"synchronize_session": "fetch"}


async def roll_over(session: AsyncSession, on: date | None = None) -> int:
    """Archive what is past, promote what is due. Returns how many changed."""
    today = on or datetime.now(UTC).date()

    archived = (
        (
            await session.execute(
                update(Puzzle)
                .where(Puzzle.status == "live", Puzzle.puzzle_date < today)
                .values(status="archived")
                .returning(Puzzle.id)
                .execution_options(**_SYNC)
            )
        )
        .scalars()
        .all()
    )

    # Only approved becomes live. A draft is something nobody has read, and no
    # amount of calendar makes it playable.
    promoted = (
        (
            await session.execute(
                update(Puzzle)
                .where(Puzzle.status == "approved", Puzzle.puzzle_date <= today)
                .values(status="live")
                .returning(Puzzle.id)
                .execution_options(**_SYNC)
            )
        )
        .scalars()
        .all()
    )

    if archived or promoted:
        logger.info("puzzle rollover: %d live, %d archived", len(promoted), len(archived))
    return len(archived) + len(promoted)
