"""Outbound search and enrichment backends. Callers of the module never see these.

Every function returns GeoNames ids so the service has one currency to work in.
"""

import re
from typing import Any, Final
from urllib.parse import quote

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

_TIMEOUT: Final = 2.0

#: Wikimedia refuses the default python-httpx agent with a 403, so this is not
#: politeness: without it, every Wikidata and Wikipedia lookup fails and the
#: citable half of the etymology chain silently falls through to the model.
#: Their policy asks for a product name and a way to make contact.
_WIKI_HEADERS: Final = {"User-Agent": "NameScape/0.1 (+https://github.com/DasolLim/FindPlaces)"}
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
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_WIKI_HEADERS) as client:
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


#: Sections that are about the name rather than the place.
_NAME_SECTIONS: Final = ("etymology", "toponymy", "name", "names", "origin of the name")

#: Phrases that mark a lead sentence as being about the name.
_NAME_MARKERS: Final = (
    "name derives",
    "name comes from",
    "named after",
    "named for",
    "takes its name",
    "the name is",
    "the name means",
)

_HEADING: Final = re.compile(r"^=+\s*(.+?)\s*=+$", re.MULTILINE)


def wikipedia_url(name: str, language: str) -> str:
    """Where an extract came from, so the interface can cite it."""
    return f"https://{language}.wikipedia.org/wiki/{quote(name.replace(' ', '_'))}"


def _tidy(sentence: str) -> str:
    collapsed = " ".join(sentence.split())
    return collapsed if collapsed.endswith(".") else f"{collapsed}."


def _sentences(body: str) -> list[str]:
    return [part.strip() for part in body.replace("\n", " ").split(". ") if part.strip()]


def _sections(extract: str) -> tuple[str, list[tuple[str, str]]]:
    """The lead, then every (heading, body) pair, headings already stripped."""
    headings = list(_HEADING.finditer(extract))
    lead = extract[: headings[0].start()] if headings else extract

    sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(extract)
        sections.append((heading.group(1).casefold(), extract[heading.end() : end]))
    return lead, sections


def name_sentence(extract: str) -> str | None:
    """The first sentence that is about this name, or None.

    Section first, lead second, and nowhere else. Scanning the whole article for
    a phrase once gave Birmingham an etymology drawn from a sentence about other
    places whose names end in "-ley": true of those places, false of this one,
    and stored as a cited high-confidence answer. A sentence about the name has
    to be somewhere that is talking about this subject.
    """
    lead, sections = _sections(extract)

    for heading, body in sections:
        if any(title == heading or title in heading.split() for title in _NAME_SECTIONS):
            found = _sentences(body)
            if not found:
                continue
            # A statement about the name beats the section's preamble: these
            # sections often open by explaining that several forms exist.
            for sentence in found:
                if any(marker in sentence.casefold() for marker in _NAME_MARKERS):
                    return _tidy(sentence)
            return _tidy(found[0])

    for sentence in _sentences(lead):
        if any(marker in sentence.casefold() for marker in _NAME_MARKERS):
            return _tidy(sentence)

    return None


async def wikipedia_etymology(name: str, language: str) -> str | None:
    """A sentence from the article that is about the name itself.

    Most articles say nothing about their subject's name, so this returns None
    far more often than not. That is the point: silence hands the question to
    the next tier rather than dressing up a first paragraph as an etymology.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_WIKI_HEADERS) as client:
            response = await client.get(
                f"https://{language}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": "1",
                    "redirects": "1",
                    "format": "json",
                    "titles": name,
                },
            )
            response.raise_for_status()
            pages: dict[str, Any] = response.json()["query"]["pages"]
    except (httpx.HTTPError, ValueError, KeyError):
        return None

    for page in pages.values():
        extract = page.get("extract")
        if extract:
            found = name_sentence(extract)
            if found is not None:
                return found
    return None
