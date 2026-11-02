"""Gazetteer search."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.modules import gazetteer
from app.routes.deps import SessionDep
from app.text import strip_nul

router = APIRouter()


class SearchResult(BaseModel):
    """One gazetteer hit, with whether anyone has already claimed it."""

    id: int
    geonames_id: int
    name: str
    feature_class: str
    feature_code: str
    country_code: str | None
    admin1: str | None
    tier: int
    lat: float
    lon: float
    claimed_by: str | None


class SearchResponse(BaseModel):
    results: list[SearchResult]


CountryDep = Annotated[str | None, Query(min_length=2, max_length=2)]


@router.get("/api/search")
async def search_places(
    q: str,
    session: SessionDep,
    country: CountryDep = None,
    #: Widens the fuzzy threshold. What the empty state offers instead of a
    #: dead end.
    broad: bool = False,
) -> SearchResponse:
    found = await gazetteer.search(session, strip_nul(q), country_code=country, broad=broad)
    return SearchResponse(results=[SearchResult(**asdict(result)) for result in found])
