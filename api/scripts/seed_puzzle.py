"""Put a playable puzzle on today's date, for development and browser tests.

Development only, and no model involved: the clues are written here so the play
path can be exercised without an OPENROUTER_API_KEY. Real puzzles come from
scripts/generate_puzzles.py and are approved by a person.

    uv run python scripts/seed_puzzle.py            # unclaimed place, today
    uv run python scripts/seed_puzzle.py --name Dull

Any existing puzzle for today is replaced, along with attempts at it, so a
browser test can run twice.
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Place, Puzzle
from app.modules.puzzles import generation

#: An unclaimed place with a country, so the derived clues have something to
#: say and solving it can be followed by claiming it.
_PICK = text(
    "SELECT id FROM places p "
    "WHERE p.country_code IS NOT NULL "
    "  AND p.tier IN (1, 2) "
    "  AND NOT EXISTS (SELECT 1 FROM discoveries d WHERE d.place_id = p.id) "
    "  AND (CAST(:name AS text) IS NULL OR p.name = CAST(:name AS text)) "
    "ORDER BY p.population DESC LIMIT 1"
)


async def main(name: str | None) -> None:
    today = datetime.now(UTC).date()

    async with SessionLocal() as session:
        place_id = (await session.execute(_PICK, {"name": name})).scalar_one_or_none()
        if place_id is None:
            raise SystemExit("no unclaimed tier 1 or 2 place found; run `make seed` first")

        await session.execute(
            text(
                "DELETE FROM puzzle_attempts WHERE puzzle_id IN "
                "(SELECT id FROM puzzles WHERE puzzle_date = :today OR place_id = :place_id)"
            ),
            {"today": today, "place_id": place_id},
        )
        await session.execute(
            text("DELETE FROM puzzles WHERE puzzle_date = :today OR place_id = :place_id"),
            {"today": today, "place_id": place_id},
        )

        place = (await session.execute(select(Place).where(Place.id == place_id))).scalars().one()
        clues = generation.clues_for(place, "A place whose name means something odd.")

        session.add(
            Puzzle(
                puzzle_date=today,
                place_id=place.id,
                clues=clues,
                status="live",
                generated_by="dev/seed",
            )
        )
        await session.commit()

    print(f"puzzle for {today}: {place.name} ({place.country_code})")
    for index, clue in enumerate(clues, start=1):
        print(f"  {index}. {clue}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=None, help="pick a place by exact name")
    parsed = parser.parse_args()
    asyncio.run(main(parsed.name))
