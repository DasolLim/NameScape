import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime
from hmac import compare_digest
from typing import Annotated, Any, Final, Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import languages, observability, ratelimit, scheduler
from app.cache import build_client, get_redis
from app.config import settings
from app.db import engine, get_session
from app.models import Place, User
from app.modules import accounts, contests, discoveries, eligibility, gazetteer, puzzles, viewport
from app.modules.accounts import bookmarks, guests, share_card
from app.modules.contests import activity
from app.modules.gazetteer import corrections
from app.modules.puzzles import play
from app.text import StripNulMiddleware, strip_nul


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start the scheduled jobs, where this process is the sort that can.

    A long-running server runs them in-process. Serverless does not: every
    function instance would start its own scheduler, so there the same jobs are
    invoked by cron over HTTP. See scheduler.should_run.
    """
    running = None
    if scheduler.should_run():
        running = scheduler.build_scheduler()
        running.start()
        logger.info("scheduler started: %s", [job.id for job in running.get_jobs()])
    try:
        yield
    finally:
        if running is not None:
            running.shutdown(wait=False)


app = FastAPI(title="NameScape API", lifespan=lifespan)


logger = logging.getLogger(__name__)


# Middleware cannot use FastAPI dependencies, so the client lives on app.state
# where a test can substitute it.
observability.configure(app)
# Outermost: nothing downstream should ever see a NUL byte.
app.add_middleware(StripNulMiddleware)
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
    admin1: str | None
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
    #: Widens the fuzzy threshold. What the empty state offers instead of a
    #: dead end.
    broad: bool = False,
) -> SearchResponse:
    found = await gazetteer.search(session, strip_nul(q), country_code=country, broad=broad)
    return SearchResponse(results=[SearchResult(**asdict(result)) for result in found])


class ErrorResponse(BaseModel):
    detail: str


def _errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Declare the failures a route can actually produce.

    Contract fuzzing treats an undocumented status code as a defect, and it is
    right to: a client generated from this schema would not know to handle it.
    """
    described = {
        400: "Malformed request body",
        401: "Not signed in",
        403: "Not allowed",
        404: "Not found",
        409: "Conflict",
        422: "Refused",
        428: "An etymology is required first",
        429: "Too many requests",
        503: "Writes are temporarily unavailable",
    }
    return {code: {"model": ErrorResponse, "description": described[code]} for code in codes}


#: Every write passes the rate limiter, which can refuse or be unavailable,
#: and a body that is not JSON at all is a 400 rather than a 422.
WRITE_ERRORS: Final = (400, 429, 503)

#: Postgres bigint. A larger id is a bad request, not a lookup that misses.
MAX_BIGINT: Final = 2**63 - 1
PlaceId = Annotated[int, Path(ge=1, le=MAX_BIGINT)]


SESSION_COOKIE = "namescape_session"
#: A guest's provisional identity. Separate from the session cookie so signing
#: in never has to think about clearing it.
GUEST_COOKIE = "namescape_guest"
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
    streak_days: int
    streak_at_risk: bool


@app.post("/api/auth/magic-link", status_code=204, responses=_errors(*WRITE_ERRORS))
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


@app.post("/api/auth/session", responses=_errors(401, *WRITE_ERRORS))
async def create_session(
    body: SessionRequest,
    session: SessionDep,
    response: Response,
    namescape_guest: Annotated[str | None, Cookie()] = None,
) -> Me:
    # The guest cookie goes in so authenticate() can adopt the claim behind it.
    signed_in = await accounts.authenticate(session, body.token, namescape_guest)
    if signed_in is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    await session.commit()

    if namescape_guest is not None:
        # Spent whether or not it carried a claim, and leaving it would let a
        # signed-out visitor in this browser inherit somebody's old session.
        response.delete_cookie(GUEST_COOKIE)

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
    session: SessionDep, namescape_session: Annotated[str | None, Cookie()] = None
) -> Me | None:
    if namescape_session is None:
        return None
    signed_in = await accounts.authenticate(session, namescape_session)
    return None if signed_in is None else Me(username=signed_in.username)


SHARE_CARD_MAX_AGE: Final = 60 * 60


@app.get(
    "/api/passport/{username}/card.png",
    response_class=Response,
    responses=_errors(404),
)
async def read_share_card(username: str, session: SessionDep) -> Response:
    found = await accounts.passport(session, strip_nul(username))
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")

    return Response(
        content=share_card.render(found),
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={SHARE_CARD_MAX_AGE}"},
    )


@app.get("/api/users/{username}", responses=_errors(404))
async def read_profile(username: str, session: SessionDep) -> Profile:
    found = await accounts.profile(session, strip_nul(username))
    if found is None:
        raise HTTPException(status_code=404, detail="No such user")
    return Profile(**asdict(found))


@app.get("/api/passport/{username}", responses=_errors(404))
async def read_passport(username: str, session: SessionDep) -> PassportResponse:
    found = await accounts.passport(session, strip_nul(username))
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


class ClaimRequest(BaseModel):
    place_id: int
    caption: str = Field(min_length=1, max_length=140)
    etymology: str | None = None


class DiscoveryResponse(BaseModel):
    id: int
    place_id: int
    finder: str
    caption: str
    #: Set only for a guest claim: when the place is released again.
    expires_at: datetime | None = None


async def _signed_in_user(session: AsyncSession, cookie: str | None) -> User | None:
    """The account a session cookie names, if it still names one."""
    signed_in = None if cookie is None else await accounts.authenticate(session, cookie)
    if signed_in is None:
        return None
    return await session.get(User, signed_in.user_id)


async def _current_user(
    session: SessionDep, namescape_session: Annotated[str | None, Cookie()] = None
) -> User:
    user = await _signed_in_user(session, namescape_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to do that")
    return user


CurrentUser = Annotated[User, Depends(_current_user)]


@app.get("/api/places/{place_id}", responses=_errors(404))
async def read_place(
    place_id: PlaceId,
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
) -> PlaceDetail:
    place = await session.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="No such place")

    signed_in = (
        None
        if namescape_session is None
        else await accounts.authenticate(session, namescape_session)
    )
    # Eligibility depends on the viewer's language, so it is per-request. It is
    # checked for a guest too: skipping it showed "allowed" on a memorial and
    # let them write a caption before a 403 said otherwise.
    verdict = await eligibility.check(
        session, place_id, signed_in.user_id if signed_in is not None else None
    )

    row = (
        await session.execute(
            text(
                # A guest claim has no user to name, but the place is taken all
                # the same, and reporting it free offers a claim that can only
                # conflict.
                "SELECT CASE WHEN d.id IS NULL THEN NULL "
                "            ELSE COALESCE(u.username, :guest_finder) END, "
                "       ST_X(p.centroid::geometry), ST_Y(p.centroid::geometry) "
                "FROM places p LEFT JOIN discoveries d ON d.place_id = p.id "
                "LEFT JOIN users u ON u.id = d.user_id WHERE p.id = :id"
            ),
            {"id": place_id, "guest_finder": discoveries.GUEST_FINDER},
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
        etymology_confidence=place.etymology_confidence,
        etymology_source=place.etymology_source,
        name_language=languages.primary_language(place.country_code),
        claimed_by=row[0],
        bookmarked=bookmarked,
        eligibility=verdict.status.value,
        eligibility_reason=verdict.reason,
    )


class CorrectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=corrections.MAX_LENGTH)


class CorrectionResponse(BaseModel):
    id: int
    place_id: int
    status: str


@app.post(
    "/api/places/{place_id}/etymology",
    status_code=201,
    responses=_errors(401, 404, 409, 422, *WRITE_ERRORS),
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


class UserDiscoveryResponse(BaseModel):
    id: int
    place_id: int
    place_name: str
    country_code: str | None
    caption: str
    created_at: datetime
    #: Set only on a guest claim: when this place is released again.
    expires_at: datetime | None = None


class UserDiscoveriesResponse(BaseModel):
    discoveries: list[UserDiscoveryResponse]


@app.get("/api/discoveries")
async def read_my_discoveries(
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
    namescape_guest: Annotated[str | None, Cookie()] = None,
) -> UserDiscoveriesResponse:
    """Whatever the caller has claimed, account or not.

    A guest has to be able to read their own claim: it is the only way the
    deadline survives a reload, and the only way the interface can explain the
    claim control instead of offering a second one. Not a 401 either way -
    a visitor who has claimed nothing has claimed nothing.
    """
    user = await _signed_in_user(session, namescape_session)
    claimant: discoveries.Claimant | None
    if user is not None:
        claimant = discoveries.UserClaimant(user.id)
    else:
        guest_id = guests.identify(namescape_guest)
        claimant = None if guest_id is None else discoveries.GuestClaimant(guest_id)

    found = [] if claimant is None else await discoveries.for_user(session, claimant)
    return UserDiscoveriesResponse(
        discoveries=[UserDiscoveryResponse(**asdict(item)) for item in found]
    )


async def _spend_guest_allowance(request: Request, redis: Redis) -> None:
    """Three claims per address per day, hashed, in Redis only.

    Charged per attempt rather than per success, because counting only the
    ones that stuck would let one address try places all day until three did.
    """
    peer = request.client.host if request.client else "unknown"
    address = ratelimit.address_of_client(peer, request.headers.get("X-Forwarded-For"))

    try:
        used = await ratelimit.count(
            redis, ratelimit.key_for(address, "guest-claim"), ratelimit.DAY_SECONDS
        )
    except (RedisError, OSError) as unreachable:
        # Without Redis the allowance cannot be counted, and an uncounted
        # guest claim is the one thing this limit exists to prevent.
        raise HTTPException(
            status_code=503, detail="Writes are temporarily unavailable"
        ) from unreachable

    if used > settings.guest_claims_per_day:
        raise HTTPException(status_code=429, detail="Too many requests")


@app.post("/api/discoveries", status_code=201, responses=_errors(403, 409, 422, 428, *WRITE_ERRORS))
async def create_discovery(
    body: ClaimRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    redis: RedisDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
    namescape_guest: Annotated[str | None, Cookie()] = None,
) -> DiscoveryResponse:
    """Claiming is the one write that does not require an account."""
    user = await _signed_in_user(session, namescape_session)

    claimant: discoveries.Claimant
    guest: guests.Guest | None = None
    if user is not None:
        claimant = discoveries.UserClaimant(user.id)
        finder = user.username
    else:
        await _spend_guest_allowance(request, redis)
        # Written in the claim's own transaction, so a claim that fails does
        # not leave a session behind for a cookie to point at.
        guest = await guests.resolve(session, namescape_guest)
        claimant = discoveries.GuestClaimant(guest.id)
        finder = discoveries.GUEST_FINDER

    try:
        discovery = await discoveries.claim(
            session, body.place_id, claimant, body.caption, body.etymology
        )
    except discoveries.AlreadyClaimedError:
        raise HTTPException(status_code=409, detail="Someone found this one first") from None
    except discoveries.GuestLimitReachedError:
        raise HTTPException(
            status_code=403,
            detail="You already have a claim. Create an account to keep it and find more.",
        ) from None
    except discoveries.NotEligibleError as blocked:
        raise HTTPException(status_code=403, detail=str(blocked)) from None
    except discoveries.EtymologyRequiredError as needed:
        raise HTTPException(status_code=428, detail=str(needed)) from None
    except discoveries.CaptionRejectedError:
        # Deliberately vague: naming the rule teaches people to beat it.
        raise HTTPException(status_code=422, detail="That caption cannot be used") from None

    await session.commit()
    if guest is not None:
        # Only now, with the claim committed, is the cookie worth holding on to.
        response.set_cookie(
            GUEST_COOKIE,
            guest.cookie,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=guests.GUEST_TTL_SECONDS,
        )

    return DiscoveryResponse(
        id=discovery.id,
        place_id=discovery.place_id,
        finder=finder,
        caption=discovery.caption,
        expires_at=discovery.expires_at,
    )


class PuzzleGuessResponse(BaseModel):
    place_id: int
    name: str
    distance_km: float
    bearing: float
    #: One of eight, so the player is told which way to go next.
    arrow: str
    band: str
    proximity: int


class PuzzlePinResponse(BaseModel):
    lat: float
    lon: float


class PuzzleAnswerResponse(BaseModel):
    place_id: int
    name: str
    country_code: str | None
    lat: float
    lon: float
    claimed_by: str | None


class PuzzleStateResponse(BaseModel):
    puzzle_id: int
    number: int
    clues: list[str]
    guesses: list[PuzzleGuessResponse]
    solved: bool
    complete: bool
    remaining: int
    #: The last clue, earned by a fourth wrong guess. Drawn on the globe.
    pin: PuzzlePinResponse | None
    #: Withheld until the attempt is over.
    answer: PuzzleAnswerResponse | None
    share_grid: str
    streak: int


class ArchiveEntry(BaseModel):
    puzzle_id: int
    number: int
    date: date
    solved: bool
    guesses: int


class ArchiveResponse(BaseModel):
    puzzles: list[ArchiveEntry]


class GuessRequest(BaseModel):
    place_id: int = Field(ge=1, le=MAX_BIGINT)


def _state_response(state: puzzles.AttemptState) -> PuzzleStateResponse:
    return PuzzleStateResponse(
        puzzle_id=state.puzzle_id,
        number=state.puzzle_number,
        clues=state.clues,
        guesses=[
            PuzzleGuessResponse(
                place_id=guess.place_id,
                name=guess.name,
                distance_km=round(guess.distance_km, 1),
                bearing=round(guess.bearing, 1),
                arrow=guess.arrow,
                band=guess.band.name.casefold(),
                proximity=guess.proximity,
            )
            for guess in state.guesses
        ],
        solved=state.solved,
        complete=state.complete,
        remaining=state.remaining,
        pin=PuzzlePinResponse(lat=state.pin[0], lon=state.pin[1]) if state.pin else None,
        answer=(
            PuzzleAnswerResponse(
                place_id=state.answer.place_id,
                name=state.answer.name,
                country_code=state.answer.country_code,
                lat=state.answer.lat,
                lon=state.answer.lon,
                claimed_by=state.answer.claimed_by,
            )
            if state.answer
            else None
        ),
        share_grid=state.share_grid,
        streak=state.streak,
    )


async def _existing_player(
    session: AsyncSession, session_cookie: str | None, guest_cookie: str | None
) -> discoveries.Claimant | None:
    """Whoever is already known, without creating anybody.

    Reading the puzzle must not mint a guest session for somebody who opens the
    page and never guesses.
    """
    user = await _signed_in_user(session, session_cookie)
    if user is not None:
        return discoveries.UserClaimant(user.id)
    guest_id = guests.identify(guest_cookie)
    return None if guest_id is None else discoveries.GuestClaimant(guest_id)


@app.get("/api/puzzle")
async def read_puzzle(
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
    namescape_guest: Annotated[str | None, Cookie()] = None,
) -> PuzzleStateResponse | None:
    """Today's puzzle and this player's progress. Null on a day without one."""
    puzzle = await puzzles.today(session)
    if puzzle is None:
        return None

    player = await _existing_player(session, namescape_session, namescape_guest)
    if player is None:
        # Nobody to look up, so nothing has been earned: the opening state.
        return PuzzleStateResponse(
            puzzle_id=puzzle.id,
            number=play.puzzle_number(puzzle.puzzle_date),
            clues=list(puzzle.clues[:1]),
            guesses=[],
            solved=False,
            complete=False,
            remaining=play.MAX_GUESSES,
            pin=None,
            answer=None,
            share_grid="",
            streak=0,
        )

    return _state_response(await puzzles.state_for(session, puzzle.id, player))


@app.post("/api/puzzle/{puzzle_id}/guess", responses=_errors(404, 409, *WRITE_ERRORS))
async def guess_puzzle(
    puzzle_id: PlaceId,
    body: GuessRequest,
    response: Response,
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
    namescape_guest: Annotated[str | None, Cookie()] = None,
) -> PuzzleStateResponse:
    """Guess, and hear how close it came. No account needed to play."""
    user = await _signed_in_user(session, namescape_session)
    guest: guests.Guest | None = None
    if user is not None:
        player: discoveries.Claimant = discoveries.UserClaimant(user.id)
    else:
        # Guessing is the first moment there is anything to remember.
        guest = await guests.resolve(session, namescape_guest)
        player = discoveries.GuestClaimant(guest.id)

    try:
        await puzzles.guess(session, puzzle_id, player, body.place_id)
    except puzzles.NoPuzzleError:
        raise HTTPException(status_code=404, detail="No such puzzle") from None
    except puzzles.UnknownPlaceError:
        raise HTTPException(status_code=404, detail="No such place") from None
    except puzzles.AttemptCompleteError:
        raise HTTPException(status_code=409, detail="You have finished today's puzzle") from None

    state = await puzzles.state_for(session, puzzle_id, player)
    await session.commit()

    if guest is not None:
        response.set_cookie(
            GUEST_COOKIE,
            guest.cookie,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=guests.GUEST_TTL_SECONDS,
        )
    return _state_response(state)


@app.get("/api/puzzle/archive", responses=_errors(401))
async def read_puzzle_archive(
    session: SessionDep, namescape_session: Annotated[str | None, Cookie()] = None
) -> ArchiveResponse:
    """Puzzles that have been and gone, and how they went.

    Account-gated, per Addendum A. No answers: it is for replaying, not for
    reading ahead. The refusal says what an account is for here rather than
    the generic "sign in", because the archive is a reason to have one.
    """
    user = await _signed_in_user(session, namescape_session)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Past puzzles are kept with your account. Create one to play them.",
        )

    rows = (
        await session.execute(
            text(
                "SELECT z.id, z.puzzle_date, "
                "       COALESCE(a.solved, false), COALESCE(a.guess_count, 0) "
                "FROM puzzles z "
                "LEFT JOIN puzzle_attempts a "
                "  ON a.puzzle_id = z.id AND a.user_id = :user_id "
                "WHERE z.status = 'archived' "
                "ORDER BY z.puzzle_date DESC LIMIT 90"
            ),
            {"user_id": user.id},
        )
    ).all()

    return ArchiveResponse(
        puzzles=[
            ArchiveEntry(
                puzzle_id=int(row[0]),
                number=play.puzzle_number(row[1]),
                date=row[1],
                solved=bool(row[2]),
                guesses=int(row[3]),
            )
            for row in rows
        ]
    )


class CronResult(BaseModel):
    job: str
    changed: int


#: The scheduled work, by name. Each already takes its own Redis lock, so an
#: overlapping invocation is safe whether it came from a timer or from cron.
_CRON_JOBS: Final = {
    "resolve-due": scheduler.resolve_due_once,
    "release-expired": scheduler.release_expired_once,
    "puzzle-rollover": scheduler.roll_over_once,
}


@app.get("/api/cron/{job}", responses=_errors(401, 404))
async def run_scheduled_job_get(
    job: str, request: Request, session: SessionDep, redis: RedisDep
) -> CronResult:
    """Vercel's scheduler invokes with GET. See run_scheduled_job."""
    return await run_scheduled_job(job, request, session, redis)


@app.post("/api/cron/{job}", responses=_errors(401, 404))
async def run_scheduled_job(
    job: str, request: Request, session: SessionDep, redis: RedisDep
) -> CronResult:
    """Run one scheduled job. For platforms with no long-running process.

    Declared for GET as well, because Vercel's scheduler invokes with GET and
    does not follow redirects: POST alone would deploy cleanly and never run
    once. Two endpoints rather than one multi-method route, because FastAPI
    gives both methods of a multi-method route the same operation id, and the
    generated frontend types then fail to compile on a duplicate identifier.

    Also the way to force a job by hand, which is what makes a plan with
    once-a-day cron usable: a contest can be resolved on demand rather than
    waited for. Cron delivery is best effort and may miss a run or repeat one,
    which is safe here: each job takes a Redis lock and each is idempotent.

    Fails closed on an unset secret. These endpoints resolve contests and
    release claims, so an open one would be a way to force either at will.
    """
    supplied = (request.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
    if not settings.cron_secret or not compare_digest(supplied, settings.cron_secret):
        raise HTTPException(status_code=401, detail="Not authorised")

    runner = _CRON_JOBS.get(job)
    if runner is None:
        raise HTTPException(status_code=404, detail="No such job")

    return CronResult(job=job, changed=await runner(redis, session))


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
    # Constrained at the edge: a coordinate off the globe is a bad request.
    west: Annotated[float, Query(ge=-180, le=180)],
    south: Annotated[float, Query(ge=-90, le=90)],
    east: Annotated[float, Query(ge=-180, le=180)],
    north: Annotated[float, Query(ge=-90, le=90)],
    zoom: Annotated[int, Query(ge=0, le=22)],
    namescape_session: Annotated[str | None, Cookie()] = None,
) -> ViewportResponse:
    signed_in = (
        None
        if namescape_session is None
        else await accounts.authenticate(session, namescape_session)
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


@app.post("/api/bookmarks/{place_id}", status_code=204, responses=_errors(401, 404, *WRITE_ERRORS))
async def add_bookmark(place_id: PlaceId, session: SessionDep, user: CurrentUser) -> Response:
    if await session.get(Place, place_id) is None:
        raise HTTPException(status_code=404, detail="No such place")
    await bookmarks.add(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@app.delete("/api/bookmarks/{place_id}", status_code=204, responses=_errors(401, *WRITE_ERRORS))
async def remove_bookmark(place_id: PlaceId, session: SessionDep, user: CurrentUser) -> Response:
    await bookmarks.remove(session, user.id, place_id)
    await session.commit()
    return Response(status_code=204)


@app.get("/api/bookmarks", responses=_errors(401))
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


@app.post("/api/proposals", status_code=201, responses=_errors(401, 422, *WRITE_ERRORS))
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


@app.post("/api/votes", status_code=204, responses=_errors(401, 403, 409, *WRITE_ERRORS))
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
    place_id: PlaceId,
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
) -> ContestBoard:
    state = await contests.state_for(session, place_id)
    signed_in = (
        None
        if namescape_session is None
        else await accounts.authenticate(session, namescape_session)
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


class ActivityResponse(BaseModel):
    """What the chrome needs to show a reason to return, in one request."""

    contests_closing_soon: int
    #: None when nobody is signed in.
    streak_days: int | None
    streak_at_risk: bool


@app.get("/api/activity")
async def read_activity(
    session: SessionDep,
    namescape_session: Annotated[str | None, Cookie()] = None,
) -> ActivityResponse:
    signed_in = (
        None
        if namescape_session is None
        else await accounts.authenticate(session, namescape_session)
    )

    streak_days: int | None = None
    at_risk = False
    if signed_in is not None:
        mine = await accounts.passport(session, signed_in.username)
        if mine is not None:
            streak_days = mine.streak_days
            at_risk = mine.streak_at_risk

    return ActivityResponse(
        contests_closing_soon=await activity.closing_soon(session),
        streak_days=streak_days,
        streak_at_risk=at_risk,
    )
