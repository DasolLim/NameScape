"""Drafting the daily puzzle, offline and in batches.

Internal. Nothing here may run while a player waits: the puzzle has to be
deterministic, identical worldwide, instant, and unchanged if it is regenerated,
and a live model call is none of those. It also cannot be allowed to fail at
00:00 UTC in front of everyone at once.

So a batch drafts ninety days ahead, writes rows as drafts, and a person
approves them. Ninety days of buffer means a bad batch is caught long before
anybody plays it.
"""

import logging
import re
import unicodedata
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml
from sqlalchemy import select
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import LLMClient
from app.models import Place, Puzzle
from app.modules.moderation.normalize import normalize

logger = logging.getLogger(__name__)

COUNTRIES_PATH: Final = Path(__file__).parents[3] / "data" / "countries.yaml"

#: How many times to ask again before giving up on a place. A model that leaks
#: the name three times running is not going to stop on the fourth.
MAX_ATTEMPTS: Final = 3

#: How many rows to consider per place wanted. The quality gate runs in Python,
#: so a plain SQL LIMIT would hand back exactly as many rows as days needed,
#: discard most of them, and leave a ninety day batch short.
_OVERFETCH: Final = 20

#: Below this, a shared fragment is a coincidence rather than a leak: "by"
#: appears in half the English language.
_MIN_FRAGMENT: Final = 4

#: Anything that is not a letter or a digit, in any script. The moderation
#: module's fold cannot be reused here: it strips everything outside a-z, so a
#: Cyrillic alternate name folds to nothing and cannot be checked at all.
_SEPARATORS: Final = re.compile(r"[^\w]", re.UNICODE)

_FEATURE_NAMES: Final[dict[str, str]] = {
    "P": "a populated place",
    "H": "a body of water",
    "T": "a landform",
    "A": "an administrative area",
    "L": "an area or park",
    "S": "a building or structure",
    "R": "a road or railway",
    "V": "a wood or forest",
}

#: Rough scale, from population. Deliberately coarse: an exact figure would
#: narrow the answer far too much for a second clue.
_SCALES: Final = (
    (0, "with almost nobody living there"),
    (1_000, "a village"),
    (20_000, "a town"),
    (200_000, "a city"),
    (2_000_000, "a large city"),
)

#: The quality gate. A resolved etymology is not automatically a usable clue:
#: "The orthography of the name has varied over the ages" is true, cited, and
#: says nothing about what the name means. Asking a model to write a meaning
#: clue from that is asking it to invent one, so the place is skipped instead.
_MEANING_MARKERS: Final = (
    "mean",
    "derive",
    "named after",
    "named for",
    "comes from",
    "came from",
    "takes its name",
    "from the ",
    "from a ",
    "from old",
    "from latin",
    "from greek",
    "referring to",
    "literally",
)


def states_a_meaning(etymology: str | None) -> bool:
    """Whether an etymology says what the name means, rather than merely
    discussing the name."""
    if not etymology:
        return False
    lowered = etymology.casefold()
    return any(marker in lowered for marker in _MEANING_MARKERS)


_SYSTEM: Final = (
    "You write clues for a daily geography puzzle. You never reveal the answer, "
    "and you return only JSON."
)

_PROMPT: Final = (
    "Place name: {name}\n"
    "What the name means: {etymology}\n"
    "Feature type: {feature}\n"
    "Country: {country}\n\n"
    "Write a one-sentence clue describing what the name MEANS, without using "
    "the name, any part of it, or any obvious cognate. Do not mention the "
    "country or the region.\n"
    'Return JSON: {{"clue": str, "leaks_name": bool}}'
)

#: A place is puzzle material only if all of this holds. The etymology is the
#: first clue, the country carries two more, and a restricted zone is off
#: limits everywhere else in the product so it is off limits here.
_CANDIDATES_SQL: Final = """
    SELECT p.id
    FROM places p
    WHERE p.etymology IS NOT NULL
      AND p.tier IN (1, 2)
      AND p.country_code IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM puzzles z WHERE z.place_id = p.id)
      AND NOT EXISTS (
          SELECT 1 FROM restricted_zones r WHERE ST_Intersects(p.centroid, r.geom)
      )
    ORDER BY p.tier, p.population DESC, p.id
    LIMIT :limit
"""


class GenerationError(Exception):
    """The batch failed. Deliberately fatal: a bad row is worse than no row."""


@lru_cache(maxsize=1)
def _countries() -> dict[str, dict[str, str]]:
    """Code to name and continent. Two of the five clues come from here."""
    try:
        loaded = yaml.safe_load(COUNTRIES_PATH.read_text())
    except (OSError, yaml.YAMLError):
        logger.exception("country lookup unavailable")
        return {}
    return {
        str(code).upper(): {"name": str(entry["name"]), "continent": str(entry["continent"])}
        for code, entry in (loaded or {}).items()
    }


def _scale(population: int) -> str:
    label = _SCALES[0][1]
    for floor, name in _SCALES:
        if population >= floor:
            label = name
    return label


def _fold(text: str) -> str:
    """Case, accents, spacing and punctuation all removed, script preserved."""
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFKD", normalize(text))
        if not unicodedata.combining(char)
    )
    return _SEPARATORS.sub("", stripped)


def fragments(place: Place) -> list[str]:
    """Every string that would give the answer away.

    The name, each word of it, and every alternate name, folded so that case,
    spacing and diacritics are not a way around the check.
    """
    names = [place.name, *(place.alternate_names or [])]
    found: list[str] = []
    for name in names:
        folded = _fold(name)
        if len(folded) >= _MIN_FRAGMENT:
            found.append(folded)
        for word in _fold_words(name):
            if len(word) >= _MIN_FRAGMENT:
                found.append(word)
    return sorted(set(found), key=len, reverse=True)


def _fold_words(text: str) -> list[str]:
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFKD", normalize(text))
        if not unicodedata.combining(char)
    )
    return [_SEPARATORS.sub("", word) for word in re.split(r"[\s\-]+", stripped) if word]


def names_the_place(clue: str, place: Place) -> bool:
    """Whether the name, or a word of it, appears in the clue.

    The plain check, and the only one that makes sense for text we wrote
    ourselves: a country called Djibouti is also a city called Djibouti, and
    the country clue would hand that over.
    """
    folded = _fold(clue)
    return any(fragment in folded for fragment in fragments(place))


def leaks(clue: str, place: Place) -> bool:
    """Whether a model's clue gives the answer away.

    Both directions. A fragment of the name inside the clue is the obvious
    leak; a word of the clue appearing *inside* the name catches a compound
    like Ffynnongroyw, where "groyw" is not a separate word at all.

    Deliberately strict, and deliberately not applied to our own derived
    clues: "a populated place" shares "place" with Placerville, which would
    abort a ninety day batch over a template we wrote. There are millions of
    candidate places and only one chance to make a puzzle trivial, so a false
    rejection costs a retry and a missed one costs the day.

    Run regardless of what the model said about itself, because a model that
    leaks the name is usually the same model that reports it did not.
    """
    if names_the_place(clue, place):
        return True

    known = fragments(place)
    return any(
        len(word) >= _MIN_FRAGMENT and any(word in fragment for fragment in known)
        for word in _fold_words(clue)
    )


async def draft(client: LLMClient, place: Place) -> str:
    """One clue for one place, or raise. Retries a leak and a bad shape alike."""
    for attempt in range(MAX_ATTEMPTS + 1):
        reply = await client.complete_json(
            _PROMPT.format(
                name=place.name,
                etymology=place.etymology,
                feature=_FEATURE_NAMES.get(place.feature_class, "a place"),
                country=place.country_code,
            ),
            system=_SYSTEM,
        )
        clue = _clue_from(reply)
        if clue is None:
            logger.warning("attempt %d for %s returned nothing usable", attempt + 1, place.name)
            continue
        if isinstance(reply, dict) and reply.get("leaks_name") is True:
            logger.info("attempt %d for %s self-reported a leak", attempt + 1, place.name)
            continue
        if leaks(clue, place):
            logger.warning("attempt %d for %s leaked the name", attempt + 1, place.name)
            continue
        return clue

    raise GenerationError(f"no usable clue for {place.name} after {MAX_ATTEMPTS + 1} attempts")


def _clue_from(reply: Any) -> str | None:
    if not isinstance(reply, dict):
        return None
    clue = reply.get("clue")
    if not isinstance(clue, str) or not clue.strip():
        return None
    return clue.strip()


async def candidates(session: AsyncSession, limit: int) -> list[Place]:
    """Places worth guessing at, best first. Up to `limit` of them."""
    ids = (
        (await session.execute(sql(_CANDIDATES_SQL), {"limit": limit * _OVERFETCH})).scalars().all()
    )
    if not ids:
        return []

    known = _countries()
    places = (await session.execute(select(Place).where(Place.id.in_(ids)))).scalars().all()
    by_id = {place.id: place for place in places}
    # Ordered as the query returned them, and only where a continent is known
    # (two of the five clues are the continent and the country) and the
    # etymology actually says what the name means.
    usable = [
        by_id[place_id]
        for place_id in ids
        if place_id in by_id
        and (by_id[place_id].country_code or "").upper() in known
        and states_a_meaning(by_id[place_id].etymology)
    ]
    return usable[:limit]


def clues_for(place: Place, meaning: str) -> list[str]:
    """The reveal order: meaning, then feature and scale, then continent, then
    country. The fifth reveal is the pin, which is the place itself.
    """
    entry = _countries()[(place.country_code or "").upper()]
    return [
        meaning,
        f"It is {_FEATURE_NAMES.get(place.feature_class, 'a place')}, {_scale(place.population)}.",
        entry["continent"],
        entry["name"],
    ]


async def generate(session: AsyncSession, client: LLMClient, start: date, limit: int) -> int:
    """Draft up to `limit` consecutive days from `start`. Returns how many.

    A date that already has a puzzle is skipped rather than replaced: the
    puzzle for a given day is fixed once it exists, and regenerating it would
    change the answer under anyone who had already played.
    """
    taken = set(
        (
            await session.execute(
                select(Puzzle.puzzle_date).where(
                    Puzzle.puzzle_date >= start,
                    Puzzle.puzzle_date < start + timedelta(days=limit),
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = [start + timedelta(days=offset) for offset in range(limit)]
    days = [day for day in wanted if day not in taken]
    if not days:
        return 0

    pool = await candidates(session, limit=len(days))
    written = 0
    for day, place in zip(days, pool, strict=False):
        clues = clues_for(place, await draft(client, place))
        for clue in clues:
            # Ours, but still checked: a country called Djibouti is also a city
            # called Djibouti, and the country clue would hand that over.
            if names_the_place(clue, place):
                raise GenerationError(f"derived clue leaks {place.name}: {clue}")

        session.add(
            Puzzle(
                puzzle_date=day,
                place_id=place.id,
                clues=clues,
                status="draft",
                generated_by=client.model,
            )
        )
        await session.flush()
        written += 1

    return written
