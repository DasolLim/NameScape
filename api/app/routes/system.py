"""Operator endpoints: health and metrics."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app import observability
from app.config import settings
from app.db import engine

router = APIRouter()


@router.get("/metrics", response_class=Response)
async def read_metrics() -> Response:
    return Response(content=observability.render_metrics(), media_type="text/plain")


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


@router.get("/api/health")
async def health() -> Health:
    # Checked together: a slow dependency should not double the wait.
    db_up, redis_up = await asyncio.gather(_postgres_reachable(), _redis_reachable())
    return Health(status="ok" if db_up and redis_up else "degraded", db=db_up, redis=redis_up)
