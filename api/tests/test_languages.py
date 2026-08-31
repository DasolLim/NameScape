"""Which language to reason about a name in.

Shared by eligibility, which asks whether a submitter can read a name, and the
gazetteer, which asks what language to look a name up in. The order inside a
country matters to the second one: picking Welsh for Liverpool sends the lookup
to the wrong Wikipedia and would tell a model the wrong language entirely.
"""

from app import languages


def test_a_multilingual_country_resolves_to_its_primary_language() -> None:
    assert languages.primary_language("GB") == "en"
    assert languages.primary_language("CA") == "en"
    assert languages.primary_language("CH") == "de"
    assert languages.primary_language("BE") == "nl"


def test_case_does_not_matter() -> None:
    assert languages.primary_language("gb") == "en"


def test_an_unlisted_or_missing_country_yields_no_language() -> None:
    """No language is a real answer: it is what stops a model being asked to
    explain a name in a language nobody has established."""
    assert languages.primary_language(None) is None
    assert languages.primary_language("ZZ") is None


def test_every_language_of_a_country_is_still_available() -> None:
    """Eligibility needs the whole set, not just the primary one."""
    spoken = languages.languages_of("GB")

    assert spoken is not None
    assert {"en", "cy", "gd"} <= spoken
