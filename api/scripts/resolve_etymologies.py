"""Resolve what names mean, offline.

Run as a batch, never from a request. Tiers 1 to 3 are cheap enough to serve on
demand, but tier 4 is a model call, and a model call while a user waits is slow,
nondeterministic, and able to fail for everyone at once. Etymology is
effectively immutable, so resolving ahead of time costs nothing and the answer
is cached on the row forever.

    uv run python scripts/resolve_etymologies.py --limit 200
    uv run python scripts/resolve_etymologies.py --country GB --limit 500

Without OPENROUTER_API_KEY the model tier is skipped and the citable tiers still
run, which is a supported way to work: those are the answers worth having.
"""

import argparse
import asyncio
import logging

from sqlalchemy import text

from app.db import SessionLocal
from app.modules import gazetteer

logger = logging.getLogger(__name__)

#: Unresolved means confidence IS NULL. A resolved 'unknown' is an answer and
#: is deliberately not picked up again.
_UNRESOLVED = text(
    "SELECT id FROM places "
    "WHERE etymology_confidence IS NULL "
    "  AND (CAST(:country AS char(2)) IS NULL "
    "       OR country_code = CAST(:country AS char(2))) "
    "ORDER BY population DESC, tier, id "
    "LIMIT :limit"
)


async def main(limit: int, country: str | None) -> None:
    async with SessionLocal() as session:
        ids = (
            (await session.execute(_UNRESOLVED, {"limit": limit, "country": country}))
            .scalars()
            .all()
        )

        tally: dict[str, int] = {}
        for place_id in ids:
            place = await gazetteer.enrich(session, place_id)
            confidence = place.etymology_confidence or "none"
            tally[confidence] = tally.get(confidence, 0) + 1
            # Committed one at a time: a batch that dies partway should keep
            # every answer it already paid for.
            await session.commit()

    print(f"resolved {len(ids)} places")
    for confidence, count in sorted(tally.items()):
        print(f"  {confidence}: {count}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--country", default=None, help="ISO 3166-1 alpha-2")
    parsed = parser.parse_args()
    asyncio.run(main(parsed.limit, parsed.country))
