"""Which language a place's name is likely to be in.

GeoNames carries no language tag per name, so the country is the best cheap
signal available. Deliberately coarse, and deliberately willing to say it does
not know: an unlisted country yields no language, which is what stops a model
being asked to explain a name in a language nobody has established.

Shared rather than owned by one module: eligibility asks whether a submitter
can read a name, and the gazetteer asks what language to reason about it in.
Two copies of this table would drift.
"""

from typing import Final

#: Written languages by country, **most primary first**, for the countries we
#: hold places in. Order is load-bearing: primary_language takes the first, and
#: an alphabetical set gave Welsh for Liverpool, which sent the lookup to the
#: Welsh Wikipedia and would have told a model the wrong language outright.
#: Extend as the gazetteer grows; an unlisted country asks for etymology.
_PRIMARY_LANGUAGES: Final[dict[str, tuple[str, ...]]] = {
    "AT": ("de",),
    "AR": ("es",),
    "AU": ("en",),
    "BE": (
        "nl",
        "fr",
        "de",
    ),
    "BR": ("pt",),
    "CA": (
        "en",
        "fr",
    ),
    "CH": (
        "de",
        "fr",
        "it",
    ),
    "DE": ("de",),
    "FR": ("fr",),
    "GB": (
        "en",
        "cy",
        "gd",
    ),
    "GL": (
        "kl",
        "da",
    ),
    "IE": (
        "en",
        "ga",
    ),
    "IT": ("it",),
    "JP": ("ja",),
    "NL": ("nl",),
    "NO": ("no",),
    "NZ": (
        "en",
        "mi",
    ),
    "PK": (
        "ur",
        "en",
    ),
    "RU": ("ru",),
    "TH": ("th",),
    "TR": ("tr",),
    "US": ("en",),
}


def languages_of(country_code: str | None) -> frozenset[str] | None:
    """Every written language of a country, or None if it is not listed."""
    if country_code is None:
        return None
    spoken = _PRIMARY_LANGUAGES.get(country_code.upper())
    return None if spoken is None else frozenset(spoken)


def primary_language(country_code: str | None) -> str | None:
    """One language to reason in, or None when there is no basis for a guess."""
    if country_code is None:
        return None
    spoken = _PRIMARY_LANGUAGES.get(country_code.upper())
    return spoken[0] if spoken else None
