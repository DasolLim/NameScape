"""The gazetteer's three public operations.

Typesense, Photon, trigram ranking and Wikidata all live behind these.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability
from app.models import Place
from app.modules.discoveries import GUEST_FINDER
from app.modules.gazetteer import backends

#: A suggestion list, not a result page.
DEFAULT_LIMIT: Final = 10
_TRIGRAM_FLOOR: Final = 0.35


@dataclass(frozen=True, slots=True)
class PlaceResult:
    id: int
    geonames_id: int
    name: str
    feature_class: str
    feature_code: str
    country_code: str | None
    #: State or province code, so two places of the same name are telling apart.
    admin1: str | None
    tier: int
    lat: float
    lon: float
    claimed_by: str | None


#: An exact match on a tiny place should beat a larger place that only shares
#: its prefix, but a genuinely major city should still win. Weighted as a
#: million people: typing "Dull" finds Dull (population 84) ahead of
#: Dullewala (50,000), while typing "Tor" still finds Toronto ahead of Tor.
EXACT_MATCH_BONUS: Final = 1_000_000

#: Enough candidates to rank well without scanning the world.
_CANDIDATE_POOL: Final = 400

#: pg_trgm's default match threshold, and the looser one used when a visitor
#: asks to widen the search rather than accept a dead end.
NORMAL_THRESHOLD: Final = 0.3
BROAD_THRESHOLD: Final = 0.12

#: Stage one: an indexed prefix scan, which is what almost every keystroke
#: needs. text_pattern_ops turns LIKE 'query%' into a range scan.
_PREFIX_SQL = text(
    """
    SELECT p.geonames_id,
           CASE WHEN p.feature_class = 'P' THEN 0 ELSE 1 END AS is_settlement,
           p.population
             + CASE WHEN p.name_normalized = :q THEN :bonus ELSE 0 END AS prominence,
           length(p.name) AS name_length
    FROM places p
    WHERE p.name_normalized LIKE :prefix
      AND (CAST(:country AS char(2)) IS NULL
           OR p.country_code = CAST(:country AS char(2)))
    ORDER BY prominence DESC
    LIMIT :pool
    """
)

#: Stage two, only when the prefix scan is thin: the trigram operator, which
#: the GIN index over names and alternate names can actually serve. Using
#: similarity() > n instead would force a sequential scan.
_FUZZY_SQL = text(
    """
    SELECT p.geonames_id,
           CASE WHEN p.feature_class = 'P' THEN 0 ELSE 1 END AS is_settlement,
           p.population AS prominence,
           length(p.name) AS name_length
    FROM places p
    WHERE p.search_text % CAST(:q AS text)
      AND (CAST(:country AS char(2)) IS NULL
           OR p.country_code = CAST(:country AS char(2)))
    ORDER BY similarity(p.search_text, CAST(:q AS text)) DESC, p.population DESC
    LIMIT :pool
    """
)

_HYDRATE_SQL = text(
    """
    SELECT p.id, p.geonames_id, p.name, p.feature_class, p.feature_code,
           p.country_code, p.admin1, p.tier,
           ST_Y(p.centroid::geometry) AS lat, ST_X(p.centroid::geometry) AS lon,
           CASE WHEN d.id IS NULL THEN NULL
                ELSE COALESCE(u.username, :guest_finder) END AS claimed_by
    FROM places p
    LEFT JOIN discoveries d ON d.place_id = p.id
    LEFT JOIN users u ON u.id = d.user_id
    WHERE p.geonames_id = ANY(:ids)
    """
)


async def _trigram_ids(
    session: AsyncSession,
    query: str,
    country_code: str | None,
    limit: int,
    broad: bool = False,
) -> list[int]:
    """Prefix first, fuzzy only if that came up short. Both index-backed."""
    normalized = query.casefold()
    # SET LOCAL keeps the change inside this transaction, and the trigram
    # index still serves the operator at any threshold.
    # set_config takes a parameter where SET LOCAL cannot; the final `true`
    # scopes it to this transaction.
    await session.execute(
        text("SELECT set_config('pg_trgm.similarity_threshold', :threshold, true)"),
        {"threshold": str(BROAD_THRESHOLD if broad else NORMAL_THRESHOLD)},
    )
    params = {
        "q": normalized,
        "prefix": f"{normalized}%",
        "country": country_code,
        "bonus": EXACT_MATCH_BONUS,
        "pool": _CANDIDATE_POOL,
    }

    #: (stage, geonames_id, is_settlement, prominence, name_length)
    candidates: list[tuple[int, int, int, int, int]] = [
        (0, int(row[0]), int(row[1]), int(row[2]), int(row[3]))
        for row in (await session.execute(_PREFIX_SQL, params)).all()
    ]

    if len(candidates) < limit:
        seen = {candidate[1] for candidate in candidates}
        candidates.extend(
            (1, int(row[0]), int(row[1]), int(row[2]), int(row[3]))
            for row in (await session.execute(_FUZZY_SQL, params)).all()
            if int(row[0]) not in seen
        )

    # Prefix hits rank ahead of fuzzy ones; within a stage, settlements first,
    # then prominence, then the shorter name.
    candidates.sort(key=lambda c: (c[0], c[2], -c[3], c[4]))
    return [candidate[1] for candidate in candidates[:limit]]


async def _hydrate(session: AsyncSession, geonames_ids: list[int]) -> list[PlaceResult]:
    rows = (
        (await session.execute(_HYDRATE_SQL, {"ids": geonames_ids, "guest_finder": GUEST_FINDER}))
        .mappings()
        .all()
    )
    by_geonames_id = {
        int(row["geonames_id"]): PlaceResult(
            id=int(row["id"]),
            geonames_id=int(row["geonames_id"]),
            name=row["name"],
            feature_class=row["feature_class"],
            feature_code=row["feature_code"],
            country_code=row["country_code"],
            admin1=row["admin1"],
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
    broad: bool = False,
) -> list[PlaceResult]:
    """Find places by name or alternate name, typo-tolerantly.

    `broad` widens the fuzzy threshold, which is what the empty state offers
    instead of a dead end.
    """
    normalized = query.strip()
    if not normalized:
        return []

    with observability.search_seconds.time():
        return await _search(session, normalized, country_code, limit, broad)


async def _search(
    session: AsyncSession,
    normalized: str,
    country_code: str | None,
    limit: int,
    broad: bool = False,
) -> list[PlaceResult]:
    geonames_ids = await backends.typesense_ids(normalized, country_code, limit)
    if geonames_ids is None:
        geonames_ids = await _trigram_ids(session, normalized, country_code, limit, broad)
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
