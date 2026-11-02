"""Place detail and etymology corrections."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app import languages
from app.models import Place
from app.modules import discoveries, eligibility
from app.modules.gazetteer import corrections
from app.routes.deps import (
    WRITE_ERRORS,
    CurrentUser,
    PlaceId,
    SessionCookie,
    SessionDep,
    errors,
    viewer,
)

router = APIRouter()


class PlaceDetail(BaseModel):
    id: int
    geonames_id: int
    name: str
    feature_class: str
    feature_code: str
    country_code: str | None
    tier: int
    lat: float
    lon: float
    etymology: str | None
    #: How citable the etymology is: high, medium, unverified, or unknown.
    #: Null means nobody has looked yet. The interface must never present an
    #: unverified meaning as a sourced one, so this crosses the boundary.
    etymology_confidence: str | None
    #: A URL for the citable tiers, a marker for the lexicon, a model id for
    #: the unverified tier.
    etymology_source: str | None
    #: The language the name is probably in, or null when there is no basis to
    #: guess. The reveal is offered on names a reader probably cannot read.
    name_language: str | None
    claimed_by: str | None
    bookmarked: bool
    eligibility: str
    eligibility_reason: str | None


#: Finder, coordinates and the viewer's bookmark in one round trip.
#: A guest claim has no user to name, but the place is taken all the same, and
#: reporting it free offers a claim that can only conflict.
_PLACE_EXTRAS = text(
    "SELECT CASE WHEN d.id IS NULL THEN NULL "
    "            ELSE COALESCE(u.username, :guest_finder) END, "
    "       ST_X(p.centroid::geometry), ST_Y(p.centroid::geometry), "
    "       EXISTS (SELECT 1 FROM bookmarks b "
    "               WHERE b.place_id = p.id AND b.user_id = :user_id) "
    "FROM places p LEFT JOIN discoveries d ON d.place_id = p.id "
    "LEFT JOIN users u ON u.id = d.user_id WHERE p.id = :id"
)


@router.get("/api/places/{place_id}", responses=errors(404))
async def read_place(
    place_id: PlaceId, session: SessionDep, namescape_session: SessionCookie = None
) -> PlaceDetail:
    place = await session.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="No such place")

    signed_in = await viewer(session, namescape_session)
    user_id = signed_in.user_id if signed_in is not None else None
    # Eligibility depends on the viewer's language, so it is per-request. It is
    # checked for a guest too: skipping it showed "allowed" on a memorial and
    # let them write a caption before a 403 said otherwise.
    verdict = await eligibility.check(session, place_id, user_id)

    finder, lon, lat, bookmarked = (
        await session.execute(
            _PLACE_EXTRAS,
            {"id": place_id, "user_id": user_id, "guest_finder": discoveries.GUEST_FINDER},
        )
    ).one()

    return PlaceDetail(
        id=place.id,
        geonames_id=place.geonames_id,
        name=place.name,
        feature_class=place.feature_class,
        feature_code=place.feature_code,
        country_code=place.country_code,
        tier=place.tier,
        lon=float(lon),
        lat=float(lat),
        etymology=place.etymology,
        etymology_confidence=place.etymology_confidence,
        etymology_source=place.etymology_source,
        name_language=languages.primary_language(place.country_code),
        claimed_by=finder,
        bookmarked=bool(bookmarked),
        eligibility=verdict.status.value,
        eligibility_reason=verdict.reason,
    )


class CorrectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=corrections.MAX_LENGTH)


class CorrectionResponse(BaseModel):
    id: int
    place_id: int
    status: str


@router.post(
    "/api/places/{place_id}/etymology",
    status_code=201,
    responses=errors(401, 404, 409, 422, *WRITE_ERRORS),
)
async def correct_etymology(
    place_id: PlaceId, body: CorrectionRequest, session: SessionDep, user: CurrentUser
) -> CorrectionResponse:
    """File a correction. Held for review, never applied on the spot.

    An account is required because the contributor credit is the point: a
    correction is somebody putting their name to a claim about the world.
    """
    try:
        filed = await corrections.submit(session, place_id, user.id, body.text)
    except corrections.UnknownPlaceError:
        raise HTTPException(status_code=404, detail="No such place") from None
    except corrections.DuplicateError:
        raise HTTPException(status_code=409, detail="You have already said that") from None
    except corrections.RejectedError:
        # Vague on purpose, exactly as captions are.
        raise HTTPException(status_code=422, detail="That correction cannot be used") from None

    await session.commit()
    return CorrectionResponse(id=filed.id, place_id=filed.place_id, status=filed.status)
