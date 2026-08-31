"""Draft daily puzzles, ninety days ahead.

    uv run python scripts/generate_puzzles.py --days 90
    uv run python scripts/generate_puzzles.py --days 7 --from 2026-10-01

Offline on purpose. The puzzle has to be deterministic, identical for every
player worldwide, instant, and unchanged if it is regenerated, and a model call
in the request path is none of those. It also cannot be allowed to fail at
00:00 UTC in front of everyone at once.

Rows are written as drafts. Nothing is playable until a person approves it with
scripts/approve_puzzles.py, and ninety days of buffer means a bad batch is
caught long before anybody plays it.

Needs OPENROUTER_API_KEY. Without it there is no clue to write and the batch
refuses to start rather than writing rows with something worse in them.
"""

import argparse
import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

from app import llm
from app.db import SessionLocal
from app.modules.puzzles import generation

logger = logging.getLogger(__name__)


async def main(days: int, start: date) -> None:
    client = llm.build_client()
    if client is None:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. Puzzle clues need a model, and a "
            "batch without one would write rows nobody should play."
        )

    async with SessionLocal() as session:
        try:
            written = await generation.generate(session, client, start, limit=days)
        except generation.GenerationError as failed:
            # Nothing is committed: a bad row is worse than a missing day.
            await session.rollback()
            raise SystemExit(f"batch failed, nothing written: {failed}") from failed
        await session.commit()

    print(f"drafted {written} puzzles from {start} using {client.model}")
    if written < days:
        print(f"  {days - written} days skipped: already drafted, or no candidates left")
    print("nothing is playable until scripts/approve_puzzles.py approves it")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument(
        "--from",
        dest="start",
        default=None,
        help="ISO date to start from. Defaults to tomorrow, UTC.",
    )
    parsed = parser.parse_args()
    first = (
        date.fromisoformat(parsed.start)
        if parsed.start
        else datetime.now(UTC).date() + timedelta(days=1)
    )
    asyncio.run(main(parsed.days, first))
