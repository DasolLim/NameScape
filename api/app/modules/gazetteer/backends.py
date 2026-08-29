"""Outbound search and enrichment backends. Callers of the module never see these.

Every function returns GeoNames ids so the service has one currency to work in.
"""

from typing import Any, Final

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

_TIMEOUT: Final = 2.0
#: How close a Photon hit must land to a gazetteer record to be the same place.
_PHOTON_MATCH_METRES: Final = 25_000


async def typesense_ids(query: str, country_code: str | None, limit: int) -> list[int] | None:
    """GeoNames ids from the search index.

    Returns None when the index is unavailable, which is distinct from "no
    results": None means fall back to Postgres trigram search.
    """
    if not settings.typesense_url:
        return None

    params: dict[str, str] = {
        "q": query,
        "query_by": "name,alternate_names",
        "per_page": str(limit),
    }
    if country_code:
        params["filter_by"] = f"country_code:={country_code}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{settings.typesense_url}/collections/places/documents/search",
                params=params,
                headers={"X-TYPESENSE-API-KEY": settings.typesense_api_key},
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
    except (httpx.HTTPError, ValueError, KeyError):
        return None

    return [int(hit["document"]["geonames_id"]) for hit in payload.get("hits", [])]


async def photon_ids(
    session: AsyncSession, query: str, country_code: str | None, limit: int
) -> list[int]:
    """Typo-tolerant fallback.

    Photon is OSM-based and knows nothing about GeoNames, so each hit is mapped
    back to a gazetteer record by proximity plus name similarity.
    """
    if not settings.photon_url:
        return []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                f"{settings.photon_url}/api", params={"q": query, "limit": str(limit)}
            )
            response.raise_for_status()
            features = response.json().get("features", [])
    except (httpx.HTTPError, ValueError, KeyError):
        return []

    matched: list[int] = []
    for feature in features:
        coordinates = feature.get("geometry", {}).get("coordinates")
        name = feature.get("properties", {}).get("name")
        if not coordinates or not name:
            continue

        row = (
            await session.execute(
                text(
                    "SELECT geonames_id FROM places "
                    "WHERE ST_DWithin(centroid, ST_MakePoint(:lon, :lat)::geography, :radius) "
                    "  AND (CAST(:country AS char(2)) IS NULL "
                    "       OR country_code = CAST(:country AS char(2))) "
                    "ORDER BY similarity(name_normalized, :name) DESC LIMIT 1"
                ),
                {
                    "lon": float(coordinates[0]),
                    "lat": float(coordinates[1]),
                    "radius": _PHOTON_MATCH_METRES,
                    "country": country_code,
                    "name": name.casefold(),
                },
            )
        ).first()
        if row is not None and row[0] not in matched:
            matched.append(int(row[0]))

    return matched


async def wikidata_etymology(wikidata_id: str) -> str | None:
    """Resolve 'named after' (P138) into a sentence, or None when absent."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            entity = (
                await client.get(
                    f"{settings.wikidata_url}/wiki/Special:EntityData/{wikidata_id}.json"
                )
            ).json()
            claims = entity["entities"][wikidata_id]["claims"]
            named_after = claims["P138"][0]["mainsnak"]["datavalue"]["value"]["id"]

            target = (
                await client.get(
                    f"{settings.wikidata_url}/wiki/Special:EntityData/{named_after}.json"
                )
            ).json()
            label = target["entities"][named_after]["labels"]["en"]["value"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None

    return f"Named after {label}."
