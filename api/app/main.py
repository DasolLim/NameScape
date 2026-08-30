from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability, ratelimit
from app.cache import build_client, get_redis
from app.config import settings
from app.db import engine, get_session
from app.models import Place, User
from app.modules import accounts, contests, discoveries, eligibility, gazetteer, viewport
from app.modules.accounts import bookmarks, share_card

app = FastAPI(title="Toponomicon API")


# Middleware cannot use FastAPI dependencies, so the client lives on app.state
# where a test can substitute it.
observability.configure(app)
app.state.redis = build_client()


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any) -> Response:
    identifier = observability.new_request_id(request.headers.get("X-Request-ID"))
    token = observability.request_id.set(identifier)
    try:
        response: Response = await call_next(request)
    finally:
        observability.request_id.reset(token)
    response.headers["X-Request-ID"] = identifier
    return response


@app.get("/metrics", response_class=Response)
async def read_metrics() -> Response:
    return Response(content=observability.render_metrics(), media_type="text/plain")


@app.middleware("http")
async def rate_limit_writes(request: Request, call_next: Any) -> Response:
    """Applied to every write, so a new endpoint is covered by default."""
    if request.method in ratelimit.LIMITED_METHODS:
        try:
            await ratelimit.enforce(request, app.state.redis)
        except HTTPException as limited:
            return JSONResponse(status_code=limited.status_code, content={"detail": limited.detail})
    response: Response = await call_next(request)
    return response


class Health(BaseModel):
    """Liveness of the API and the backing services it cannot work without."""

    status: Literal["ok", "degraded"]
    db: bool
    redis: bool


async def _postgres_reachable() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def _redis_reachable() -> bool:
    client: Redis = Redis.from_url(settings.redis_url)
    try:
        return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@app.get("/api/health")
async def health() -> Health:
    db_up = await _postgres_reachable()
    redis_up = await _redis_reachable()
    return Health(status="ok" if db_up and redis_up else "degraded", db=db_up, redis=redis_up)


class SearchResult(BaseModel):
    """One gazetteer hit, with whether anyone has already claimed it."""

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


class SearchResponse(BaseModel):
    results: list[SearchResult]


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CountryDep = Annotated[str | None, Query(min_length=2, max_length=2)]


@app.get("/api/search")
async def search_places(
    q: str,
    session: SessionDep,
    country: CountryDep = None,
) -> SearchResponse:
    found = await gazetteer.search(session, q, country_code=country)
    return SearchResponse(results=[SearchResult(**asdict(result)) for result in found])


SESSION_COOKIE = "toponomicon_session"
RedisDep = Annotated[Redis, Depends(get_redis)]


class MagicLinkRequest(BaseModel):
    email: EmailStr


class SessionRequest(BaseModel):
    token: str


class Me(BaseModel):
    username: str


class Profile(BaseModel):
    username: str
    joined_at: datetime
    discoveries: int


class PassportResponse(BaseModel):
    username: str
    discoveries: int
    first_finds: int
    countries: dict[str, int]
    completion: dict[str, float]


@app.post("/api/auth/magic-link", status_code=204)
async def request_magic_link(
    body: MagicLinkRequest, session: SessionDep, redis: RedisDep
) -> Response:
    try:
        await accounts.request_magic_link(session, redis, body.email)
    except accounts.TooManyRequestsError:
        # Deliberately vague: the limit is not a hint to work around.
        raise HTTPException(status_code=429, detail="Too many requests") from None
    await session.commit()
    return Response(status_code=204)


@app.post("/api/auth/session")
async def create_session(body: SessionRequest, session: SessionDep, response: Response) -> Me:
    signed_in = await accounts.authenticate(session, body.token)
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    await session.commit()

    response.set_cookie(
        SESSION_COOKIE,
        signed_in.cookie,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=accounts.SESSION_TTL_SECONDS,
    )
    return Me(username=signed_in.username)


@app.get("/api/auth/me")
async def read_me(
    session: SessionDep, toponomicon_session: Annotated[str | None, Cookie()] = None
) -> Me | None:
    if toponomicon_session is None:
        return None
    signed_in = await accounts.authenticate(session, toponomicon_session)
    return None if signed_in is None else Me(username=signed_in.username)


SHARE_CARD_MAX_AGE: Final = 60 * 60


@app.get("/api/passport/{username}/card.png", response_class=Response)
async def read_share_card(username: str, session: SessionDep) -> Response:
    found = await accounts.passport(session, username)
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")

    return Response(
        content=share_card.render(found),
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={SHARE_CARD_MAX_AGE}"},
    )


@app.get("/api/users/{username}")
async def read_profile(username: str, session: SessionDep) -> Profile:
    found = await accounts.profile(session, username)
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")
    return Profile(**asdict(found))


@app.get("/api/passport/{username}")
async def read_passport(username: str, session: SessionDep) -> PassportResponse:
    found = await accounts.passport(session, username)
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")
    return PassportResponse(**asdict(found))


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
    claimed_by: str | None
    bookmarked: bool
    eligibility: str
    eligibility_reason: str | None


class ClaimRequest(BaseModel):
    place_id: int
    caption: str = Field(min_length=1, max_length=140)
    etymology: str | None = None


class DiscoveryResponse(BaseModel):
    id: int
    place_id: int
    finder: str
    caption: str


async def _current_user(
    session: SessionDep, toponomicon_session: Annotated[str | None, Cookie()] = None
) -> User:
    signed_in = (
        None
        if toponomicon_session is None
        else await accounts.authenticate(session, toponomicon_session)
    )
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Sign in to do that")
    user = await session.get(User, signed_in.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to do that")
    return user


CurrentUser = Annotated[User, Depends(_current_user)]


@app.get("/api/places/{place_id}")
async def read_place(
    place_id: int,
    session: SessionDep,
    toponomicon_session: Annotated[str | None, Cookie()] = None,
) -> PlaceDetail:
    place = await session.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="No such place")

    signed_in = (
        None
        if toponomicon_session is None
        else await accounts.authenticate(session, toponomicon_session)
    )
    # Eligibility depends on the viewer's language, so it is per-request.
    verdict = (
        await eligibility.check(session, place_id, signed_in.user_id)
        if signed_in is not None
        else eligibility.EligibilityVerdict(eligibility.Eligibility.ALLOWED)
    )

    row = (
        await session.execute(
            text(
                "SELECT u.username, ST_X(p.centroid::geometry), ST_Y(p.centroid::geometry) "
                "FROM places p LEFT JOIN discoveries d ON d.place_id = p.id "
                "LEFT JOIN users u ON u.id = d.user_id WHERE p.id = :id"
            ),
            {"id": place_id},
        )
    ).one()

    bookmarked = False
    if signed_in is not None:
        bookmarked = (
            await session.scalar(
                text(
                    "SELECT true FROM bookmarks WHERE user_id = :user_id AND place_id = :place_id"
                ),
                {"user_id": signed_in.user_id, "place_id": place_id},
            )
        ) is True

    return PlaceDetail(
        id=place.id,
        geonames_id=place.geonames_id,
        name=place.name,
        feature_class=place.feature_class,
        feature_code=place.feature_code,
        country_code=place.country_code,
        tier=place.tier,
        lon=float(row[1]),
        lat=float(row[2]),
        etymology=place.etymology,
        claimed_by=row[0],
        bookmarked=bookmarked,
        eligibility=verdict.status.value,
        eligibility_reason=verdict.reason,
    )


class UserDiscoveryResponse(BaseModel):
    id: int
    place_id: int
    place_name: str
    country_code: str | None
    caption: str
    created_at: datetime


class UserDiscoveriesResponse(BaseModel):
    discoveries: list[UserDiscoveryResponse]


@app.get("/api/discoveries")
async def read_my_discoveries(session: SessionDep, user: CurrentUser) -> UserDiscoveriesResponse:
    found = await discoveries.for_user(session, user.id)
    return UserDiscoveriesResponse(
        discoveries=[UserDiscoveryResponse(**asdict(item)) for item in found]
    )


@app.post("/api/discoveries", status_code=201)
async def create_discovery(
    body: ClaimRequest, session: SessionDep, user: CurrentUser
) -> DiscoveryResponse:
    try:
        discovery = await discoveries.claim(
            session, body.place_id, user.id, body.caption, body.etymology
        )
    except discoveries.AlreadyClaimedError:
        raise HTTPException(status_code=409, detail="Someone found this one first") from None
    except discoveries.NotEligibleError as blocked:
        raise HTTPException(status_code=403, detail=str(blocked)) from None
    except discoveries.EtymologyRequiredError as needed:
        raise HTTPException(status_code=428, detail=str(needed)) from None
    except discoveries.CaptionRejectedError:
        # Deliberately vague: naming the rule teaches people to beat it.
        raise HTTPException(status_code=422, detail="That caption cannot be used") from None

    await session.commit()
    return DiscoveryResponse(
        id=discovery.id,
        place_id=discovery.place_id,
        finder=user.username,
        caption=discovery.caption,
    )


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


@app.get("/api/viewport")
async def read_viewport(
    session: SessionDep,
    redis: RedisDep,
    west: float,
    south: float,
    east: float,
    north: float,
    zoom: int,
    toponomicon_session: Annotated[str | None, Cookie()] = None,
) -> ViewportResponse:
    signed_in = (
        None
        if toponomicon_session is None
        else await accounts.authenticate(session, toponomicon_session)
    )
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


class SavedPlaceResponse(BaseModel):
    place_id: int
    name: str
    country_code: str | None
    lon: float
    lat: float


class BookmarksResponse(BaseModel):
    bookmarks: list[SavedPlaceResponse]


@app.post("/api/bookmarks/{place_id}", status_code=204)
async def add_bookmark(place_id: int, session: SessionDep, user: CurrentUser) -> Response:
    if await session.get(Place, place_id) is None:
        raise HTTPException(status_code=404, detail="No such place")
    await bookmarks.add(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@app.delete("/api/bookmarks/{place_id}", status_code=204)
async def remove_bookmark(place_id: int, session: SessionDep, user: CurrentUser) -> Response:
    await bookmarks.remove(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@app.get("/api/bookmarks")
async def read_bookmarks(session: SessionDep, user: CurrentUser) -> BookmarksResponse:
    saved = await bookmarks.list_for(session, user.id)
    return BookmarksResponse(bookmarks=[SavedPlaceResponse(**asdict(item)) for item in saved])


class ProposalRequest(BaseModel):
    place_id: int
    text: str = Field(min_length=1, max_length=60)


class ProposalResponse(BaseModel):
    id: int
    text: str
    agree: int
    disagree: int
    score: int
    is_incumbent: bool
    #: True when the signed-in viewer wrote it; they cannot vote for their own.
    is_yours: bool = False


class VoteRequest(BaseModel):
    proposal_id: int
    value: int = Field(ge=-1, le=1)


class ContestBoard(BaseModel):
    place_id: int
    nickname: str | None
    leading_candidate: str | None
    closes_at: datetime | None
    reopens_at: datetime | None
    quorum: int
    proposals: list[ProposalResponse]


@app.post("/api/proposals", status_code=201)
async def create_proposal(
    body: ProposalRequest, session: SessionDep, user: CurrentUser
) -> ProposalResponse:
    try:
        proposal = await contests.propose(session, body.place_id, user.id, body.text)
    except contests.ProposalRejectedError:
        raise HTTPException(status_code=422, detail="That nickname cannot be used") from None

    await session.commit()
    return ProposalResponse(
        id=proposal.id,
        text=proposal.text,
        agree=proposal.agree,
        disagree=proposal.disagree,
        score=proposal.agree - proposal.disagree,
        is_incumbent=proposal.is_incumbent,
    )


@app.post("/api/votes", status_code=204)
async def cast_vote(body: VoteRequest, session: SessionDep, user: CurrentUser) -> Response:
    try:
        await contests.vote(session, body.proposal_id, user.id, body.value)
    except contests.SelfVoteError:
        raise HTTPException(
            status_code=403, detail="You cannot vote for your own proposal"
        ) from None
    except contests.NotEligibleToVoteError:
        raise HTTPException(
            status_code=403,
            detail="Voting opens once your account is two days old and you have found a place",
        ) from None
    except contests.ContestClosedError:
        raise HTTPException(status_code=409, detail="This contest has closed") from None

    await session.commit()
    return Response(status_code=204)


@app.get("/api/contests/{place_id}")
async def read_contest(
    place_id: int,
    session: SessionDep,
    toponomicon_session: Annotated[str | None, Cookie()] = None,
) -> ContestBoard:
    state = await contests.state_for(session, place_id)
    signed_in = (
        None
        if toponomicon_session is None
        else await accounts.authenticate(session, toponomicon_session)
    )
    yours: set[int] = set()
    if signed_in is not None:
        rows = await session.execute(
            text("SELECT id FROM proposals WHERE place_id = :place_id AND user_id = :user_id"),
            {"place_id": place_id, "user_id": signed_in.user_id},
        )
        yours = {int(row[0]) for row in rows}
    return ContestBoard(
        place_id=state.place_id,
        nickname=state.nickname,
        leading_candidate=state.leading_candidate,
        closes_at=state.closes_at,
        reopens_at=state.reopens_at,
        quorum=state.quorum,
        proposals=[ProposalResponse(**asdict(p), is_yours=p.id in yours) for p in state.proposals],
    )
