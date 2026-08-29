"""GeoNames dump import. Internal to the gazetteer module."""

from pathlib import Path
from typing import Final

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place

#: P populated, H hydrographic, T terrain. Everything else is not a place we play on.
ALLOWED_FEATURE_CLASSES: Final = frozenset({"P", "H", "T"})

TIER_1_POPULATION: Final = 500_000
TIER_2_POPULATION: Final = 10_000

#: GeoNames carries no size attribute for water bodies, so tier 1 hydro is the
#: codes that are inherently vast. Great-Lakes-class lakes need curation.
TIER_1_FEATURE_CODES: Final = frozenset({"OCN", "SEA", "GULF"})
TIER_2_FEATURE_CODES: Final = frozenset({"LK", "LKS", "BAY", "SD", "MT", "PK", "ISL"})

_GEONAMES_COLUMNS: Final = 19


def assign_tier(feature_code: str, population: int) -> int:
    """1 major, 2 notable, 3 minor. Drives contest quorum, nothing else."""
    if population > TIER_1_POPULATION or feature_code in TIER_1_FEATURE_CODES:
        return 1
    if population > TIER_2_POPULATION or feature_code in TIER_2_FEATURE_CODES:
        return 2
    return 3


def _row_to_values(fields: list[str]) -> dict[str, object] | None:
    if len(fields) < _GEONAMES_COLUMNS or fields[6] not in ALLOWED_FEATURE_CLASSES:
        return None

    name = fields[1]
    population = int(fields[14] or 0)
    alternate = [part for part in fields[3].split(",") if part]

    return {
        "geonames_id": int(fields[0]),
        "name": name,
        "name_normalized": name.casefold(),
        "alternate_names": alternate,
        "feature_class": fields[6],
        "feature_code": fields[7],
        "country_code": fields[8] or None,
        "admin1": fields[10] or None,
        "centroid": f"SRID=4326;POINT({float(fields[5])} {float(fields[4])})",
        "tier": assign_tier(fields[7], population),
        "population": population,
    }


async def import_geonames(session: AsyncSession, dump: Path) -> int:
    """Load a GeoNames dump into places. Idempotent on geonames_id."""
    imported = 0

    with dump.open(encoding="utf-8") as handle:
        for line in handle:
            values = _row_to_values(line.rstrip("\n").split("\t"))
            if values is None:
                continue

            statement = insert(Place).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[Place.geonames_id],
                    set_={key: statement.excluded[key] for key in values if key != "geonames_id"},
                )
            )
            imported += 1

    await session.flush()
    return imported
