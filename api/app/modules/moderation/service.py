"""Moderation: one call, five stages behind it.

Applies to captions and nickname proposals. Never to places.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Final, Literal

from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.moderation import classifier, normalize

logger = logging.getLogger(__name__)

DUPLICATE_SIMILARITY: Final = 0.85


class Verdict(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class ScreenResult:
    """What the caller is allowed to know. Never why something was rejected."""

    verdict: Verdict
    duplicate_of: int | None = None


@dataclass(frozen=True, slots=True)
class ScreenContext:
    place_id: int
    kind: Literal["caption", "proposal"]


@lru_cache(maxsize=1)
def _blocklist() -> tuple[str, ...]:
    path = Path(settings.blocklist_path)
    if not path.is_absolute():
        path = Path(__file__).parents[3] / path
    if not path.exists():
        logger.error("blocklist missing at %s; every submission will be rejected", path)
        return ()

    terms = [
        normalize.fold_for_matching(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return tuple(term for term in terms if term)


def _reject(reason: str, context: ScreenContext) -> ScreenResult:
    # The reason is logged and never returned: telling users which rule they
    # hit teaches them to beat it.
    logger.info("moderation rejected", extra={"reason": reason, "place_id": context.place_id})
    return ScreenResult(Verdict.REJECT)


async def _near_duplicate(
    session: AsyncSession, normalized: str, context: ScreenContext
) -> int | None:
    row = (
        await session.execute(
            sql(
                "SELECT id FROM proposals "
                "WHERE place_id = :place_id "
                "  AND similarity(normalized_text, :text) >= CAST(:floor AS real) "
                "ORDER BY similarity(normalized_text, :text) DESC LIMIT 1"
            ),
            {"place_id": context.place_id, "text": normalized, "floor": DUPLICATE_SIMILARITY},
        )
    ).first()
    return None if row is None else int(row[0])


async def screen(session: AsyncSession, text: str, context: ScreenContext) -> ScreenResult:
    """Accept, reject, or merge a submission. Fails closed on every error."""
    normalized = normalize.normalize(text)
    if not normalized:
        return _reject("empty after normalisation", context)

    folded = normalize.fold_for_matching(text)
    if any(term in folded for term in _blocklist()):
        return _reject("blocklist", context)

    if classifier.breaker.is_open:
        return _reject("classifier circuit open", context)

    try:
        categories = await classifier.classify(normalized)
    except Exception:
        classifier.breaker.record_failure()
        logger.exception("classifier unavailable; failing closed")
        return _reject("classifier unavailable", context)

    classifier.breaker.record_success()
    if categories.any_positive:
        return _reject("classified", context)

    if context.kind == "proposal":
        duplicate = await _near_duplicate(session, normalized, context)
        if duplicate is not None:
            return ScreenResult(Verdict.DUPLICATE, duplicate_of=duplicate)

    return ScreenResult(Verdict.ACCEPT)
