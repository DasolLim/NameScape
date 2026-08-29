from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_session
from app.modules import gazetteer

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
