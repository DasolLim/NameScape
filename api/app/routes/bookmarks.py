"""Personal saves. Account required."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.models import Place
from app.modules.accounts import bookmarks
from app.routes.deps import WRITE_ERRORS, CurrentUser, PlaceId, SessionDep, errors

router = APIRouter()


class SavedPlaceResponse(BaseModel):
    place_id: int
    name: str
    country_code: str | None
    lon: float
    lat: float


class BookmarksResponse(BaseModel):
    bookmarks: list[SavedPlaceResponse]


@router.post(
    "/api/bookmarks/{place_id}", status_code=204, responses=errors(401, 404, *WRITE_ERRORS)
)
async def add_bookmark(place_id: PlaceId, session: SessionDep, user: CurrentUser) -> Response:
    if await session.get(Place, place_id) is None:
        raise HTTPException(status_code=404, detail="No such place")
    await bookmarks.add(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@router.delete("/api/bookmarks/{place_id}", status_code=204, responses=errors(401, *WRITE_ERRORS))
async def remove_bookmark(place_id: PlaceId, session: SessionDep, user: CurrentUser) -> Response:
    await bookmarks.remove(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/api/bookmarks", responses=errors(401))
async def read_bookmarks(session: SessionDep, user: CurrentUser) -> BookmarksResponse:
    saved = await bookmarks.list_for(session, user.id)
    return BookmarksResponse(bookmarks=[SavedPlaceResponse(**asdict(item)) for item in saved])
