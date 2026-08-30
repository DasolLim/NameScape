"""Bookmarks: three trivial operations on a two-column table.

Not a module of its own. Wrapping an insert, a delete and a select behind a
facade would be exactly the shallow module PRD 8.3 warns against; they live
here because PRD 10 maps the bookmark routes to accounts.
"""

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SavedPlace:
    place_id: int
    name: str
    country_code: str | None
    lon: float
    lat: float


_LIST_SQL: Final = """
    SELECT p.id, p.name, p.country_code,
           ST_X(p.centroid::geometry) AS lon, ST_Y(p.centroid::geometry) AS lat
    FROM bookmarks b JOIN places p ON p.id = b.place_id
    WHERE b.user_id = :user_id
    ORDER BY b.created_at DESC
"""


async def add(session: AsyncSession, user_id: UUID, place_id: int) -> None:
    """Idempotent: saving twice is the same as saving once."""
    await session.execute(
        sql(
            "INSERT INTO bookmarks (user_id, place_id) VALUES (:user_id, :place_id) "
            "ON CONFLICT DO NOTHING"
        ),
        {"user_id": user_id, "place_id": place_id},
    )


async def remove(session: AsyncSession, user_id: UUID, place_id: int) -> None:
    """Idempotent: removing something absent is not an error."""
    await session.execute(
        sql("DELETE FROM bookmarks WHERE user_id = :user_id AND place_id = :place_id"),
        {"user_id": user_id, "place_id": place_id},
    )


async def list_for(session: AsyncSession, user_id: UUID) -> list[SavedPlace]:
    rows = (await session.execute(sql(_LIST_SQL), {"user_id": user_id})).all()
    return [
        SavedPlace(
            place_id=int(row[0]),
            name=row[1],
            country_code=row[2],
            lon=float(row[3]),
            lat=float(row[4]),
        )
        for row in rows
    ]
