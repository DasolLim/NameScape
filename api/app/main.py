from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, EmailStr
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_redis
from app.config import settings
from app.db import engine, get_session
from app.modules import accounts, gazetteer

app = FastAPI(title="Toponomicon API")


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
