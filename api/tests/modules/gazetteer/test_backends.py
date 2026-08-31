"""Outbound etymology lookups. No test makes a real request.

Wikimedia refuses a generic library User-Agent outright, so this is not a
politeness detail: without a descriptive one, every Wikipedia and Wikidata
lookup returns 403 and the whole citable half of the chain silently falls
through to the model.
"""

from typing import Any, ClassVar

import httpx
import pytest

from app.modules.gazetteer import backends

MANCHESTER = {
    "query": {
        "pages": {
            "1": {
                "extract": (
                    "Manchester is a city in England. The name derives from the Roman fort "
                    "Mamucium. It has a population of many."
                )
            }
        }
    }
}


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeClient:
    """Records how it was constructed, so the headers are testable."""

    constructed: ClassVar[list[dict[str, Any]]] = []
    payload: ClassVar[Any] = MANCHESTER

    def __init__(self, **kwargs: Any) -> None:
        FakeClient.constructed.append(kwargs)

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def get(self, _url: str, params: Any = None) -> FakeResponse:
        return FakeResponse(FakeClient.payload)


@pytest.fixture(autouse=True)
def fake_http(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.constructed = []
    FakeClient.payload = MANCHESTER
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


async def test_wikipedia_identifies_itself_or_wikimedia_refuses() -> None:
    await backends.wikipedia_etymology("Manchester", "en")

    headers = FakeClient.constructed[0]["headers"]
    agent = headers["User-Agent"]
    # Descriptive: a product name and a way to reach whoever runs it. The
    # default python-httpx agent is refused with a 403.
    assert "Toponomicon" in agent
    assert "http" in agent


async def test_wikidata_identifies_itself_too() -> None:
    FakeClient.payload = {"entities": {}}

    await backends.wikidata_etymology("Q42")

    assert "Toponomicon" in FakeClient.constructed[0]["headers"]["User-Agent"]


async def test_only_a_sentence_about_the_name_is_returned() -> None:
    found = await backends.wikipedia_etymology("Manchester", "en")

    assert found == "The name derives from the Roman fort Mamucium."


def extract(text: str) -> Any:
    return {"query": {"pages": {"1": {"extract": text}}}}


async def test_an_etymology_section_is_preferred_and_its_heading_stripped() -> None:
    FakeClient.payload = extract(
        "Bristol is a city in England. It has a harbour.\n\n"
        "== History ==\nThe city grew around the river.\n\n"
        "== Toponymy ==\nThe name derives from the Old English Brycgstow, "
        "meaning assembly place by the bridge. Later spellings varied."
    )

    found = await backends.wikipedia_etymology("Bristol", "en")

    assert found == (
        "The name derives from the Old English Brycgstow, meaning assembly place by the bridge."
    )


async def test_a_section_preamble_loses_to_an_actual_statement_about_the_name() -> None:
    """Real output: Gaziantep's etymology section opens with "Due to the city's
    contact with various ethnic groups...", which is a preamble, not a meaning."""
    FakeClient.payload = extract(
        "Gaziantep is a city in Turkey.\n\n"
        "== Etymology ==\nDue to the city's contact with various cultures, several "
        "forms exist. The name comes from Antiochia ad Taurum, with gazi added in 1921."
    )

    found = await backends.wikipedia_etymology("Gaziantep", "en")

    assert found == "The name comes from Antiochia ad Taurum, with gazi added in 1921."


async def test_a_sentence_from_an_unrelated_section_is_never_used() -> None:
    """A real failure: Birmingham's article discusses other places whose names
    end in -ley, and that sentence was stored as Birmingham's etymology.\n
    A sentence about the name must be about this name."""
    FakeClient.payload = extract(
        "Birmingham is a city in England.\n\n"
        "== Suburbs ==\nThese places, with names ending in -ley, derive from "
        "Old English leah meaning woodland clearing."
    )

    assert await backends.wikipedia_etymology("Birmingham", "en") is None


async def test_the_lead_is_used_when_there_is_no_etymology_section() -> None:
    """The lead is about the subject itself, so a name sentence there is safe."""
    FakeClient.payload = extract(
        "Batman is a city in Turkey. It takes its name from the Batman River.\n\n"
        "== Economy ==\nOil was found nearby."
    )

    found = await backends.wikipedia_etymology("Batman", "en")

    assert found == "It takes its name from the Batman River."


async def test_markup_and_whitespace_never_reach_the_reader() -> None:
    FakeClient.payload = extract(
        "Leeds is a city.\n\n=== Etymology ===\n\n  The name derives   from "
        "the Brittonic Latenses.\n\n"
    )

    found = await backends.wikipedia_etymology("Leeds", "en")

    assert found is not None
    assert "=" not in found
    assert "  " not in found


async def test_an_article_that_never_discusses_its_name_returns_nothing() -> None:
    """Silence hands the question to the next tier rather than dressing up a
    first paragraph as an etymology."""
    FakeClient.payload = {"query": {"pages": {"1": {"extract": "A town in England."}}}}

    assert await backends.wikipedia_etymology("Somewhere", "en") is None


def test_the_source_url_points_at_the_article_that_was_read() -> None:
    assert backends.wikipedia_url("Newcastle upon Tyne", "en") == (
        "https://en.wikipedia.org/wiki/Newcastle_upon_Tyne"
    )
