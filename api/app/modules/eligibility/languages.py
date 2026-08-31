"""Whether a submitter can probably read the name they are naming. Internal.

The country-to-language table this rests on is shared: see app/languages.py.
The policy of erring towards asking for an etymology stays here, because it is
eligibility's call and nobody else's.
"""

from app import languages


def is_likely_foreign(country_code: str | None, ui_language: str) -> bool:
    """True when the submitter probably cannot read the name they are naming."""
    if country_code is None:
        return False
    spoken = languages.languages_of(country_code)
    if spoken is None:
        return True
    return ui_language.split("-")[0].lower() not in spoken
