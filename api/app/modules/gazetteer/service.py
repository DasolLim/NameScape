"""The gazetteer's three public operations.

Typesense, Photon, trigram ranking and Wikidata all live behind these.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability
from app.models import Place
from app.modules.gazetteer import backends

DEFAULT_LIMIT: Final = 20
_TRIGRAM_FLOOR: Final = 0.35


@dataclass(frozen=True, slots=True)
class PlaceResult:
    id: int
    geonames_id: int
    name: str
    feature_class: str
    feature_code: str
    country_code: str | None
    tier: int
    lat: float
    lon: float
    claimed_by: str | None


_RANKED_MATCH_SQL = text(
    """
    SELECT geonames_id FROM (
      SELECT p.geonames_id,
             CASE
               WHEN p.name_normalized = :q THEN 0
               WHEN EXISTS (
                 SELECT 1 FROM unnest(p.alternate_names) a WHERE lower(a) = :q
               ) THEN 1
               WHEN p.name_normalized LIKE :contains THEN 2
               WHEN EXISTS (
                 SELECT 1 FROM unnest(p.alternate_names) a WHERE lower(a) LIKE :contains
               ) THEN 3
               ELSE 4
             END AS rank,
             similarity(p.name_normalized, :q) AS sim,
             p.population
      FROM places p
      WHERE (CAST(:country AS char(2)) IS NULL
             OR p.country_code = CAST(:country AS char(2)))
        AND (
          p.name_normalized = :q
          OR p.name_normalized LIKE :contains
          OR similarity(p.name_normalized, :q) > CAST(:floor AS real)
          OR EXISTS (
            SELECT 1 FROM unnest(p.alternate_names) a
            WHERE lower(a) = :q
               OR lower(a) LIKE :contains
               OR similarity(lower(a), :q) > CAST(:floor AS real)
          )
        )
    ) ranked
    ORDER BY rank, sim DESC, population DESC
    LIMIT :limit
    """
)

_HYDRATE_SQL = text(
    """
    SELECT p.id, p.geonames_id, p.name, p.feature_class, p.feature_code,
           p.country_code, p.tier,
           ST_Y(p.centroid::geometry) AS lat, ST_X(p.centroid::geometry) AS lon,
           u.username AS claimed_by
    FROM places p
    LEFT JOIN discoveries d ON d.place_id = p.id
    LEFT JOIN users u ON u.id = d.user_id
    WHERE p.geonames_id = ANY(:ids)
    """
)


async def _trigram_ids(
    session: AsyncSession, query: str, country_code: str | None, limit: int
) -> list[int]:
    rows = await session.execute(
        _RANKED_MATCH_SQL,
        {
            "q": query.casefold(),
            "contains": f"%{query.casefold()}%",
            "country": country_code,
            "floor": _TRIGRAM_FLOOR,
            "limit": limit,
        },
    )
    return [int(row[0]) for row in rows]


async def _hydrate(session: AsyncSession, geonames_ids: list[int]) -> list[PlaceResult]:
    rows = (await session.execute(_HYDRATE_SQL, {"ids": geonames_ids})).mappings().all()
    by_geonames_id = {
        int(row["geonames_id"]): PlaceResult(
            id=int(row["id"]),
            geonames_id=int(row["geonames_id"]),
            name=row["name"],
            feature_class=row["feature_class"],
            feature_code=row["feature_code"],
            country_code=row["country_code"],
            tier=int(row["tier"]),
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            claimed_by=row["claimed_by"],
        )
        for row in rows
    }
    # The backends decided the ordering; preserve it.
    return [by_geonames_id[gid] for gid in geonames_ids if gid in by_geonames_id]


async def search(
    session: AsyncSession,
    query: str,
    *,
    country_code: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[PlaceResult]:
    """Find places by name or alternate name, typo-tolerantly."""
    normalized = query.strip()
    if not normalized:
        return []

    with observability.search_seconds.time():
        return await _search(session, normalized, country_code, limit)


async def _search(
    session: AsyncSession, normalized: str, country_code: str | None, limit: int
) -> list[PlaceResult]:
    geonames_ids = await backends.typesense_ids(normalized, country_code, limit)
    if geonames_ids is None:
        geonames_ids = await _trigram_ids(session, normalized, country_code, limit)
    if not geonames_ids:
        geonames_ids = await backends.photon_ids(session, normalized, country_code, limit)
    if not geonames_ids:
        return []

    return await _hydrate(session, geonames_ids)


async def resolve(session: AsyncSession, geonames_id: int) -> Place | None:
    """The place behind a GeoNames id, or None. Never raises for a bad id."""
    result = await session.execute(
        text("SELECT id FROM places WHERE geonames_id = :geonames_id"),
        {"geonames_id": geonames_id},
    )
    row = result.first()
    return None if row is None else await session.get(Place, int(row[0]))


async def enrich(session: AsyncSession, place_id: int) -> Place:
    """Attach etymology from Wikidata. Cached: a second call asks nothing."""
    place = await session.get(Place, place_id)
    if place is None:
        raise LookupError(f"no place with id {place_id}")

    if place.etymology is not None or place.wikidata_id is None:
        return place

    etymology = await backends.wikidata_etymology(place.wikidata_id)
    if etymology is not None:
        place.etymology = etymology
        await session.flush()

    return place
