"""How much is happening right now. Internal to the contests module.

One count, so the chrome can show a reason to come back without loading a
whole board.
"""

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

#: "Soon" is within a day, which matches the contest window itself.
CLOSING_WINDOW: Final = timedelta(hours=24)


async def closing_soon(session: AsyncSession) -> int:
    """Live contests that resolve within the next day."""
    now = datetime.now(UTC)
    counted = await session.scalar(
        sql(
            "SELECT count(*) FROM contests "
            "WHERE status IN ('open', 'runoff') "
            "  AND closes_at > :now AND closes_at <= :horizon"
        ),
        {"now": now, "horizon": now + CLOSING_WINDOW},
    )
    return int(counted or 0)
