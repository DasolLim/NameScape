"""Build Tier A restricted zones.

Two sources: OSM tags via Overpass (memorials, worship, hospitals, cemeteries,
prisons) and a hand-reviewed YAML of disputed territories. Never run from a
test; commit the Overpass output as a fixture instead.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Final

import httpx
import yaml
from sqlalchemy import text

from app.db import SessionLocal

OVERPASS_URL: Final = "https://overpass-api.de/api/interpreter"

#: PRD 7.1 Tier A, the part that derives from tags rather than curation.
TIER_A_TAGS: Final = (
    ("amenity", "place_of_worship"),
    ("historic", "memorial"),
    ("amenity", "hospital"),
    ("landuse", "cemetery"),
    ("amenity", "prison"),
)

REASONS: Final = {
    "place_of_worship": "A place of worship. Naming is disabled here.",
    "memorial": "A memorial. Naming is disabled here.",
    "hospital": "A hospital. Naming is disabled here.",
    "cemetery": "A cemetery. Naming is disabled here.",
    "prison": "A detention facility. Naming is disabled here.",
}


def overpass_query(bbox: str) -> str:
    clauses = "".join(f'way["{key}"="{value}"]({bbox});' for key, value in TIER_A_TAGS)
    return f"[out:json][timeout:180];({clauses});out geom;"


async def fetch(bbox: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(OVERPASS_URL, data={"data": overpass_query(bbox)})
        response.raise_for_status()
        return list(response.json().get("elements", []))


def to_rings(elements: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Turn Overpass ways into (WKT polygon, reason) pairs."""
    zones: list[tuple[str, str]] = []
    for element in elements:
        geometry = element.get("geometry") or []
        if len(geometry) < 4:
            continue
        points = [f"{node['lon']} {node['lat']}" for node in geometry]
        if points[0] != points[-1]:
            points.append(points[0])

        tags = element.get("tags", {})
        key = next((tags[k] for k, _ in TIER_A_TAGS if k in tags), "")
        zones.append((f"POLYGON(({','.join(points)}))", REASONS.get(key, "Naming is disabled.")))
    return zones


def disputed_rings(path: Path) -> list[tuple[str, str]]:
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    zones = []
    for entry in entries:
        ring = ",".join(f"{lon} {lat}" for lon, lat in entry["ring"])
        zones.append((f"POLYGON(({ring}))", entry["reason"]))
    return zones


async def load(zones: list[tuple[str, str]], source: str) -> int:
    async with SessionLocal() as session:
        for wkt, reason in zones:
            await session.execute(
                text(
                    "INSERT INTO restricted_zones (geom, rule_type, reason, source) "
                    "VALUES (ST_GeogFromText(:wkt), 'no_nomination', :reason, :source)"
                ),
                {"wkt": f"SRID=4326;{wkt}", "reason": reason, "source": source},
            )
        await session.commit()
    return len(zones)


async def main(argv: list[str]) -> None:
    if len(argv) == 2 and argv[0] == "--fixture":
        zones = to_rings(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
        print(f"loaded {await load(zones, 'overpass-fixture')} zones from fixture")
    elif len(argv) == 2 and argv[0] == "--bbox":
        zones = to_rings(await fetch(argv[1]))
        print(f"loaded {await load(zones, 'overpass')} zones from Overpass")
    elif len(argv) == 1 and argv[0] == "--disputed":
        path = Path(__file__).parents[1] / "data" / "zones" / "disputed.yaml"
        print(f"loaded {await load(disputed_rings(path), 'reviewed-yaml')} disputed zones")
    else:
        raise SystemExit(
            "usage: build_zones.py [--bbox S,W,N,E | --fixture FILE.json | --disputed]"
        )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
