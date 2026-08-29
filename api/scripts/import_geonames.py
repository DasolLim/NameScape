"""Stream a GeoNames dump into places. Idempotent; safe to re-run."""

import asyncio
import sys
from pathlib import Path

from app.db import SessionLocal
from app.modules.gazetteer.importer import import_geonames


async def main(dump: Path) -> None:
    async with SessionLocal() as session:
        imported = await import_geonames(session, dump)
        await session.commit()
    print(f"imported {imported} places from {dump}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: import_geonames.py <geonames-dump.txt>")
    asyncio.run(main(Path(sys.argv[1])))
