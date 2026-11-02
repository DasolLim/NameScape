"""What the globe draws for the area in view."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.modules import viewport
from app.routes.deps import RedisDep, SessionCookie, SessionDep, viewer

router = APIRouter()


class ViewportFeature(BaseModel):
    lon: float
    lat: float
    count: int
    place_id: int | None
    name: str | None
    finder: str | None
    country_code: str | None
    score: int


class ViewportResponse(BaseModel):
    band: str
    features: list[ViewportFeature]
    nicknames: list[ViewportFeature]
    bookmarks: list[ViewportFeature]


@router.get("/api/viewport")
async def read_viewport(
    session: SessionDep,
    redis: RedisDep,
    # Constrained at the edge: a coordinate off the globe is a bad request.
    west: Annotated[float, Query(ge=-180, le=180)],
    south: Annotated[float, Query(ge=-90, le=90)],
    east: Annotated[float, Query(ge=-180, le=180)],
    north: Annotated[float, Query(ge=-90, le=90)],
    zoom: Annotated[int, Query(ge=0, le=22)],
    namescape_session: SessionCookie = None,
) -> ViewportResponse:
    signed_in = await viewer(session, namescape_session)
    data = await viewport.query(
        session,
        redis,
        viewport.BBox(west=west, south=south, east=east, north=north),
        zoom=zoom,
        user_id=signed_in.user_id if signed_in is not None else None,
    )
    return ViewportResponse(
        band=data.band.value,
        features=[ViewportFeature(**asdict(f)) for f in data.features],
        nicknames=[ViewportFeature(**asdict(f)) for f in data.nicknames],
        bookmarks=[ViewportFeature(**asdict(f)) for f in data.bookmarks],
    )
