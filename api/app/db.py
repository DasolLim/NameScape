from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

#: Supavisor's transaction mode. Session mode on 5432 and a direct connection
#: both keep prepared statements; only this one does not.
TRANSACTION_POOLER_PORT = 6543


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


def is_pooled(url: str) -> bool:
    """Whether this connection goes through a transaction pooler."""
    try:
        return urlsplit(url).port == TRANSACTION_POOLER_PORT
    except ValueError:
        return False


def connect_args_for(url: str) -> dict[str, Any]:
    """Driver arguments this connection needs.

    asyncpg prepares and caches statements by default. Through a transaction
    pooler the connection that prepared a statement is not the one that runs it
    next, so the cache is not a slow path but an error on the second query.
    """
    if not is_pooled(url):
        return {}
    return {"prepared_statement_cache_size": 0, "statement_cache_size": 0}


def migration_url() -> str:
    """Where Alembic should connect.

    Migrations need prepared statements, so they never go through a transaction
    pooler. Falls back to the runtime URL, which is correct anywhere unpooled.
    """
    return settings.database_url_direct or settings.database_url


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=connect_args_for(settings.database_url),
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with SessionLocal() as session:
        yield session
