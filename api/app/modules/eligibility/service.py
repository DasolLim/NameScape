"""Eligibility: one call deciding whether the game runs at a place.

This module NEVER affects rendering. The map shows every place; eligibility
gates only claiming and nominating.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Place, User
from app.modules.eligibility import languages


class Eligibility(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ETYMOLOGY_REQUIRED = "etymology_required"


@dataclass(frozen=True, slots=True)
class EligibilityVerdict:
    """Unlike moderation, the reason is returned: say plainly why the game stops."""

    status: Eligibility
    reason: str | None = None


#: Ordered so the strictest matching zone wins.
ZONE_LOOKUP_SQL: Final = """
    SELECT z.rule_type, z.reason
    FROM restricted_zones z
    JOIN places p ON ST_Intersects(z.geom, p.centroid)
    WHERE p.id = :place_id
    ORDER BY CASE z.rule_type
               WHEN 'no_nomination' THEN 0
               WHEN 'review_required' THEN 1
               ELSE 2
             END
    LIMIT 1
"""


async def check(session: AsyncSession, place_id: int, user_id: UUID) -> EligibilityVerdict:
    """Whether this user may claim or nickname this place."""
    place = await session.get(Place, place_id)
    if place is None:
        return EligibilityVerdict(Eligibility.BLOCKED, "That place is not in the gazetteer.")

    zone = (await session.execute(sql(ZONE_LOOKUP_SQL), {"place_id": place_id})).first()
    if zone is not None:
        rule_type, reason = zone[0], zone[1]
        if rule_type == "no_nomination":
            return EligibilityVerdict(Eligibility.BLOCKED, reason)
        return EligibilityVerdict(Eligibility.ETYMOLOGY_REQUIRED, reason)

    user = await session.get(User, user_id)
    ui_language = user.ui_language if user is not None else "en"
    if languages.is_likely_foreign(place.country_code, ui_language):
        return EligibilityVerdict(
            Eligibility.ETYMOLOGY_REQUIRED,
            "This name is in a language other than yours. Tell us what it means.",
        )

    return EligibilityVerdict(Eligibility.ALLOWED)
