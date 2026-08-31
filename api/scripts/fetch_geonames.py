"""Download and import a real GeoNames dump.

The committed fixture is 41 curated rows for tests. A usable gazetteer needs
the real thing, so this fetches from download.geonames.org and imports it.

  cities500     ~200k places worldwide with a population, good default
  GB CA US ...  every place in a country, including the tiny ones the
                product is actually about (Dildo has a population of 0)
  allCountries  the whole planet, 12M rows, ~400MB
"""

import asyncio
import sys
import zipfile
from pathlib import Path
from typing import Final

import httpx

from app.db import SessionLocal
from app.modules.gazetteer import regions
from app.modules.gazetteer.importer import import_geonames

BASE_URL: Final = "https://download.geonames.org/export/dump"
CACHE: Final = Path(__file__).parents[1] / ".geonames"


async def download(name: str) -> Path:
    CACHE.mkdir(exist_ok=True)
    archive = CACHE / f"{name}.zip"
    extracted = CACHE / f"{name}.txt"

    if extracted.exists():
        print(f"{name}: already downloaded")
        return extracted

    print(f"{name}: downloading…")
    async with (
        httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client,
        client.stream("GET", f"{BASE_URL}/{name}.zip") as response,
    ):
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        done = 0
        with archive.open("wb") as handle:
            async for chunk in response.aiter_bytes(1 << 20):
                handle.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done * 100 // total}%", end="", flush=True)
    print()

    with zipfile.ZipFile(archive) as bundle:
        bundle.extract(f"{name}.txt", CACHE)
    archive.unlink()
    return extracted


async def admin_names() -> regions.RegionLookup:
    """The admin1 code table, so regions read as names rather than numbers."""
    path = CACHE / "admin1CodesASCII.txt"
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        print("admin1 codes: downloading…")
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(f"{BASE_URL}/admin1CodesASCII.txt")
            response.raise_for_status()
            path.write_bytes(response.content)
    return regions.load(path)


async def main(names: list[str]) -> None:
    """Import each named dump.

    A name may carry a feature-class filter, as `US:P`, which loads only that
    class from that dump. Storage, not taste: a full country dump is mostly
    hydrography and terrain, and the US one is 470MB of which 381MB is lakes
    and hills. `US:P` keeps Boring and Dull and fits a free database tier.
    """
    lookup = await admin_names()
    print(f"admin1 codes: {len(lookup):,} regions")

    for name in names:
        dump_name, _, classes = name.partition(":")
        wanted = set(classes) if classes else None
        dump = await download(dump_name)
        print(f"{dump_name}: importing{f' classes {sorted(wanted)}' if wanted else ''}…")
        async with SessionLocal() as session:
            imported = await import_geonames(session, dump, lookup, wanted)
            await session.commit()
        print(f"{dump_name}: imported {imported:,} places")


if __name__ == "__main__":
    requested = sys.argv[1:] or ["cities500"]
    asyncio.run(main(requested))
