"""Which language a place's name is likely to be in. Internal.

GeoNames carries no language tag per name, so the country is the best cheap
signal available. This is deliberately coarse: it errs towards asking for an
etymology, which is the safe direction for Tier B.
"""

from typing import Final

#: Primary written languages by country, for the countries we hold places in.
#: Extend as the gazetteer grows; an unlisted country asks for etymology.
_PRIMARY_LANGUAGES: Final[dict[str, frozenset[str]]] = {
    "AT": frozenset({"de"}),
    "AR": frozenset({"es"}),
    "AU": frozenset({"en"}),
    "BE": frozenset({"nl", "fr", "de"}),
    "BR": frozenset({"pt"}),
    "CA": frozenset({"en", "fr"}),
    "CH": frozenset({"de", "fr", "it"}),
    "DE": frozenset({"de"}),
    "FR": frozenset({"fr"}),
    "GB": frozenset({"en", "cy", "gd"}),
    "GL": frozenset({"kl", "da"}),
    "IE": frozenset({"en", "ga"}),
    "IT": frozenset({"it"}),
    "JP": frozenset({"ja"}),
    "NL": frozenset({"nl"}),
    "NO": frozenset({"no"}),
    "NZ": frozenset({"en", "mi"}),
    "PK": frozenset({"ur", "en"}),
    "RU": frozenset({"ru"}),
    "TH": frozenset({"th"}),
    "TR": frozenset({"tr"}),
    "US": frozenset({"en"}),
}


def is_likely_foreign(country_code: str | None, ui_language: str) -> bool:
    """True when the submitter probably cannot read the name they are naming."""
    if country_code is None:
        return False
    languages = _PRIMARY_LANGUAGES.get(country_code.upper())
    if languages is None:
        return True
    return ui_language.split("-")[0].lower() not in languages
