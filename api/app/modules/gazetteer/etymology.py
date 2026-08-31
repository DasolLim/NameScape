"""Resolving what a name means, in order of how citable the source is.

Internal to the gazetteer: `enrich()` is the only way in, and it does not grow
a parameter for this. Four tiers, first hit wins:

    1. Wikidata named-after statements   high, citable
    2. Wikipedia extract                 high, citable
    3. A curated element lexicon         medium, rule-based
    4. A language model                  unverified

The order is the whole design. Language models produce confident, plausible,
false etymologies, because folk etymology is abundant in their training data
and a fluent wrong answer about a place name is indistinguishable from a right
one. So the model goes last, is never asked without a known language, is
allowed to refuse, and everything it does say is stored as unverified.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

from app import languages, llm
from app.config import settings
from app.models import Place
from app.modules.gazetteer import backends

logger = logging.getLogger(__name__)

#: Which Wikipedia to read. The reader's language, not the name's: a Turkish
#: name still has to be explained in English, and reading tr.wikipedia found
#: nothing at all because its section headings are Turkish. When the interface
#: is localised this follows the UI, never the place.
ARTICLE_LANGUAGE: Final = "en"

LEXICON_PATH: Final = Path(__file__).parents[3] / "data" / "name_elements.yaml"
#: Not a URL: rule-based, so there is nothing to link to.
LEXICON_SOURCE: Final = "lexicon:name_elements"

#: Below this a suffix match is coincidence rather than an element.
_MIN_STEM: Final = 3

_SYSTEM: Final = (
    "You explain the literal meaning of place-name components. "
    "You never speculate, and you say so when you do not know."
)

_PROMPT: Final = (
    "Place name: {name}\n"
    "Language: {language}\n"
    "Country: {country}\n\n"
    "Explain the literal meaning of the name's components.\n"
    'If you are not confident, respond {{"known": false}}. Do not speculate.\n'
    'Return JSON: {{"known": bool, "meaning": str|null, "components": [str]}}'
)


class Confidence(StrEnum):
    """How much weight the interface may put on an answer."""

    HIGH = "high"
    MEDIUM = "medium"
    UNVERIFIED = "unverified"
    #: Resolved, and the answer is that nobody knows. Not a failure, and not
    #: retried: retrying until something comes back is how a system talks
    #: itself into a fabrication.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Resolution:
    meaning: str | None
    confidence: Confidence
    source: str | None


_NOTHING: Final = Resolution(meaning=None, confidence=Confidence.UNKNOWN, source=None)


@lru_cache(maxsize=1)
def _lexicon() -> dict[str, dict[str, dict[str, str]]]:
    try:
        loaded = yaml.safe_load(LEXICON_PATH.read_text())
    except (OSError, yaml.YAMLError):
        logger.exception("name element lexicon unavailable")
        return {"suffixes": {}, "prefixes": {}}
    return {
        "suffixes": loaded.get("suffixes") or {},
        "prefixes": loaded.get("prefixes") or {},
    }


def from_lexicon(name: str) -> Resolution | None:
    """The longest matching element, so -chester beats -ter."""
    folded = name.casefold().replace(" ", "")
    lexicon = _lexicon()

    for element in sorted(lexicon["suffixes"], key=len, reverse=True):
        if folded.endswith(element) and len(folded) - len(element) >= _MIN_STEM:
            return _element_resolution(name, element, lexicon["suffixes"][element], "ends with")

    for element in sorted(lexicon["prefixes"], key=len, reverse=True):
        if folded.startswith(element) and len(folded) - len(element) >= _MIN_STEM:
            return _element_resolution(name, element, lexicon["prefixes"][element], "begins with")

    return None


def _element_resolution(
    name: str, element: str, entry: dict[str, str], position: str
) -> Resolution:
    # Phrased as what the element means, not as a claim about this settlement:
    # a suffix cannot know whether it is the whole story here.
    return Resolution(
        meaning=f"{name} {position} “-{element}”, {entry['meaning']}.",
        confidence=Confidence.MEDIUM,
        source=LEXICON_SOURCE,
    )


def _meaning_from(reply: Any) -> str | None:
    """A shape we did not ask for is not evidence of anything."""
    if not isinstance(reply, dict):
        return None
    if reply.get("known") is not True:
        return None
    meaning = reply.get("meaning")
    if not isinstance(meaning, str) or not meaning.strip():
        return None
    return meaning.strip()


async def resolve(place: Place) -> Resolution:
    """Work down the tiers. Always returns an answer, never raises."""
    if place.wikidata_id:
        found = await backends.wikidata_etymology(place.wikidata_id)
        if found is not None:
            return Resolution(
                meaning=found,
                confidence=Confidence.HIGH,
                source=f"{settings.wikidata_url}/wiki/{place.wikidata_id}",
            )

    extract = await backends.wikipedia_etymology(place.name, ARTICLE_LANGUAGE)
    if extract is not None:
        return Resolution(
            meaning=extract,
            confidence=Confidence.HIGH,
            source=backends.wikipedia_url(place.name, ARTICLE_LANGUAGE),
        )

    lexical = from_lexicon(place.name)
    if lexical is not None:
        return lexical

    # The name's language matters here and only here: it is what the model is
    # told to reason in. No language, no guess, because asking a model to
    # explain a name in a language nobody has established invites it to
    # invent one.
    language = languages.primary_language(place.country_code)
    if language is None:
        return _NOTHING

    client = llm.build_client()
    if client is None:
        return _NOTHING

    reply = await client.complete_json(
        _PROMPT.format(name=place.name, language=language, country=place.country_code or "unknown"),
        system=_SYSTEM,
    )
    meaning = _meaning_from(reply)
    if meaning is None:
        return _NOTHING

    return Resolution(meaning=meaning, confidence=Confidence.UNVERIFIED, source=client.model)
