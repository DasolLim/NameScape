"""Viewport: one call returning whatever the globe should draw at this zoom.

Bbox snapping, Redis caching, clustering thresholds and the feature cap all
live behind it.
"""

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability

# The label a guest claim renders under belongs to the claim, not to the
# renderer, so it is read from the module that owns claims.
from app.modules.discoveries import GUEST_FINDER

logger = logging.getLogger(__name__)

#: The renderer's budget. PRD 11.3: 500 pins at 55fps on mid-range Android.
MAX_FEATURES: Final = 500
CACHE_TTL_SECONDS: Final = 30


class Band(StrEnum):
    COUNTRY = "country"
    CLUSTER = "cluster"
    PIN = "pin"


def band_for(zoom: int) -> Band:
    """z0-3 country aggregates, z4-7 clusters, z8+ individual pins."""
    if zoom <= 3:
        return Band.COUNTRY
    if zoom <= 7:
        return Band.CLUSTER
    return Band.PIN


#: Snap size in degrees per band. Coarser bands tolerate coarser snapping,
#: which is what keeps a slow pan inside one cache entry.
_SNAP_DEGREES: Final[dict[Band, float]] = {
    Band.COUNTRY: 45.0,
    Band.CLUSTER: 5.0,
    Band.PIN: 0.5,
}

#: Grid used to collapse pins into clusters, per band.
_CLUSTER_DEGREES: Final = 2.0


@dataclass(frozen=True, slots=True)
class BBox:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True, slots=True)
class Feature:
    lon: float
    lat: float
    count: int = 1
    place_id: int | None = None
    name: str | None = None
    finder: str | None = None
    country_code: str | None = None
    #: The winning score, so collisions favour better-supported nicknames.
    score: int = 0


@dataclass(frozen=True, slots=True)
class ViewportData:
    band: Band
    features: list[Feature] = field(default_factory=list)
    #: Resolved nicknames in view. Rendered beneath the official name.
    nicknames: list[Feature] = field(default_factory=list)
    #: Empty unless a signed-in viewer asked.
    bookmarks: list[Feature] = field(default_factory=list)


def _clamp(value: float, limit: float) -> float:
    """Keep a coordinate on the globe.

    Contract fuzzing found that math.ceil on a near-DBL_MAX float raises
    OverflowError, so an absurd bounding box crashed the endpoint instead of
    returning an empty map.
    """
    if value != value:  # NaN
        return 0.0
    return max(-limit, min(limit, value))


def snap(bbox: BBox, zoom: int) -> BBox:
    """Widen a box out to a fixed grid so small pans share a cache entry."""
    step = _SNAP_DEGREES[band_for(zoom)]
    west = _clamp(bbox.west, 180.0)
    east = _clamp(bbox.east, 180.0)
    south = _clamp(bbox.south, 90.0)
    north = _clamp(bbox.north, 90.0)

    return BBox(
        west=max(-180.0, math.floor(west / step) * step),
        south=max(-90.0, math.floor(south / step) * step),
        east=min(180.0, math.ceil(east / step) * step),
        north=min(90.0, math.ceil(north / step) * step),
    )


def cache_key(bbox: BBox, zoom: int) -> str:
    snapped = snap(bbox, zoom)
    band = band_for(zoom)
    return f"viewport:{band}:{snapped.west:g},{snapped.south:g},{snapped.east:g},{snapped.north:g}"


#: A geography edge cannot span 180 degrees or more - PostGIS rejects it as
#: antipodal. At planet zoom the visible box is wider than that, and it means
#: "everywhere" anyway, so the spatial filter is simply dropped.
WORLD_SPAN_DEGREES: Final = 180.0

_ENVELOPE: Final = (
    "ST_Intersects(p.centroid, ST_MakeEnvelope(:west, :south, :east, :north, 4326)::geography)"
)
_EVERYWHERE: Final = "TRUE"


def spans_the_world(bbox: BBox) -> bool:
    return (bbox.east - bbox.west) >= WORLD_SPAN_DEGREES or (
        bbox.north - bbox.south
    ) >= WORLD_SPAN_DEGREES


def is_empty(bbox: BBox) -> bool:
    """A box with no area shows nothing, and PostGIS cannot describe it."""
    return bbox.east <= bbox.west or bbox.north <= bbox.south


def _spatial(bbox: BBox) -> str:
    return _EVERYWHERE if spans_the_world(bbox) else _ENVELOPE


_COUNTRY_SQL: Final = """
    SELECT p.country_code, count(*) AS n,
           ST_X(ST_Centroid(ST_Collect(p.centroid::geometry))) AS lon,
           ST_Y(ST_Centroid(ST_Collect(p.centroid::geometry))) AS lat
    FROM discoveries d JOIN places p ON p.id = d.place_id
    WHERE {spatial} AND p.country_code IS NOT NULL
    GROUP BY p.country_code
    ORDER BY n DESC
    LIMIT :limit
"""

_CLUSTER_SQL: Final = """
    SELECT count(*) AS n,
           ST_X(ST_Centroid(ST_Collect(p.centroid::geometry))) AS lon,
           ST_Y(ST_Centroid(ST_Collect(p.centroid::geometry))) AS lat
    FROM discoveries d JOIN places p ON p.id = d.place_id
    WHERE {spatial}
    GROUP BY ST_SnapToGrid(p.centroid::geometry, :grid)
    ORDER BY n DESC
    LIMIT :limit
"""

_PIN_SQL: Final = """
    SELECT p.id, p.name, COALESCE(u.username, :guest_finder) AS finder,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat,
           p.country_code
    FROM discoveries d
    JOIN places p ON p.id = d.place_id
    LEFT JOIN users u ON u.id = d.user_id
    WHERE {spatial}
    ORDER BY p.population DESC, p.tier, d.id
    LIMIT :limit
"""

_NICKNAME_SQL: Final = """
    SELECT p.id, n.text, n.score,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat
    FROM nicknames n JOIN places p ON p.id = n.place_id
    WHERE {spatial}
    ORDER BY n.score DESC
    LIMIT :limit
"""

_BOOKMARK_SQL: Final = """
    SELECT p.id, p.name,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat,
           p.country_code
    FROM bookmarks b JOIN places p ON p.id = b.place_id
    WHERE b.user_id = :user_id AND {spatial}
    LIMIT :limit
"""


def _bounds(bbox: BBox) -> dict[str, Any]:
    return {
        "west": bbox.west,
        "south": bbox.south,
        "east": bbox.east,
        "north": bbox.north,
        "limit": MAX_FEATURES,
    }


async def _load(session: AsyncSession, bbox: BBox, band: Band) -> list[Feature]:
    params = _bounds(bbox)
    spatial = _spatial(bbox)

    if band is Band.COUNTRY:
        rows = (await session.execute(sql(_COUNTRY_SQL.format(spatial=spatial)), params)).all()
        return [
            Feature(lon=float(r[2]), lat=float(r[3]), count=int(r[1]), country_code=r[0])
            for r in rows
        ]

    if band is Band.CLUSTER:
        rows = (
            await session.execute(
                sql(_CLUSTER_SQL.format(spatial=spatial)),
                {**params, "grid": _CLUSTER_DEGREES},
            )
        ).all()
        return [Feature(lon=float(r[1]), lat=float(r[2]), count=int(r[0])) for r in rows]

    rows = (
        await session.execute(
            sql(_PIN_SQL.format(spatial=spatial)),
            {**params, "guest_finder": GUEST_FINDER},
        )
    ).all()
    return [
        Feature(
            lon=float(r[3]),
            lat=float(r[4]),
            place_id=int(r[0]),
            name=r[1],
            finder=r[2],
            country_code=r[5],
        )
        for r in rows
    ]


async def _load_nicknames(session: AsyncSession, bbox: BBox) -> list[Feature]:
    rows = (
        await session.execute(sql(_NICKNAME_SQL.format(spatial=_spatial(bbox))), _bounds(bbox))
    ).all()
    return [
        Feature(
            lon=float(row[3]),
            lat=float(row[4]),
            place_id=int(row[0]),
            name=row[1],
            score=int(row[2]),
        )
        for row in rows
    ]


async def query(
    session: AsyncSession,
    redis: Redis,
    bbox: BBox,
    zoom: int,
    user_id: UUID | None = None,
) -> ViewportData:
    """What the globe should draw here. Bookmarks are never cached."""
    band = band_for(zoom)
    snapped = snap(bbox, zoom)
    if is_empty(snapped):
        return ViewportData(band=band)

    key = cache_key(bbox, zoom)

    try:
        cached = await redis.get(key)
    except (RedisError, OSError):
        # A dead cache is slow, not fatal: read straight from Postgres.
        logger.warning("viewport cache unavailable; reading from postgres")
        cached = None

    if cached is not None:
        observability.viewport_cache_total.labels(outcome="hit").inc()
        payload = json.loads(cached)
        features = [Feature(**item) for item in payload["features"]]
        nicknames = [Feature(**item) for item in payload["nicknames"]]
    else:
        observability.viewport_cache_total.labels(outcome="miss").inc()
        features = await _load(session, snapped, band)
        nicknames = await _load_nicknames(session, snapped)
        try:
            await redis.set(
                key,
                json.dumps(
                    {
                        "features": [asdict(f) for f in features],
                        "nicknames": [asdict(n) for n in nicknames],
                    }
                ),
                ex=CACHE_TTL_SECONDS,
            )
        except (RedisError, OSError):
            logger.warning("viewport cache unwritable; serving uncached")

    bookmarks: list[Feature] = []
    if user_id is not None:
        rows = (
            await session.execute(
                sql(_BOOKMARK_SQL.format(spatial=_spatial(snapped))),
                {**_bounds(snapped), "user_id": user_id},
            )
        ).all()
        bookmarks = [
            Feature(
                lon=float(r[2]), lat=float(r[3]), place_id=int(r[0]), name=r[1], country_code=r[4]
            )
            for r in rows
        ]

    return ViewportData(band=band, features=features, nicknames=nicknames, bookmarks=bookmarks)
