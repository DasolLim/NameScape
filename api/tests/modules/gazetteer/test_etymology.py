"""What a name means, and how much to trust the answer.

The chain is ordered by how citable each source is, not by how likely it is to
produce something. A fluent invented etymology is worse than no etymology at
all in a product whose premise is respecting what names actually mean, which is
why the model goes last, is skipped without a known language, and is allowed to
say it does not know.
"""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import llm
from app.modules import gazetteer
from app.modules.gazetteer import backends, etymology
from tests.factories import build_place


class FakeLLM:
    """Records every call, so "never asked" is testable rather than assumed."""

    def __init__(self, reply: dict[str, Any] | None = None) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "fake/model-1"

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """All three outbound sources silent by default. No test makes a request."""
    calls: dict[str, list[str]] = {"wikidata": [], "wikipedia": []}

    async def no_wikidata(wikidata_id: str) -> str | None:
        calls["wikidata"].append(wikidata_id)
        return None

    async def no_wikipedia(name: str, language: str) -> str | None:
        calls["wikipedia"].append(name)
        return None

    monkeypatch.setattr(backends, "wikidata_etymology", no_wikidata)
    monkeypatch.setattr(backends, "wikipedia_etymology", no_wikipedia)
    monkeypatch.setattr(llm, "build_client", lambda: None)
    return calls


def with_llm(monkeypatch: pytest.MonkeyPatch, client: FakeLLM) -> FakeLLM:
    monkeypatch.setattr(llm, "build_client", lambda: client)
    return client


async def test_wikidata_wins_and_is_citable(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    async def named_after(wikidata_id: str) -> str:
        sources["wikidata"].append(wikidata_id)
        return "Named after the Dildo family."

    monkeypatch.setattr(backends, "wikidata_etymology", named_after)
    place = await build_place(db)
    place.wikidata_id = "Q42"

    enriched = await gazetteer.enrich(db, place.id)

    assert enriched.etymology == "Named after the Dildo family."
    assert enriched.etymology_confidence == etymology.Confidence.HIGH
    assert enriched.etymology_source is not None
    assert "Q42" in enriched.etymology_source
    # Nothing further is asked once a citable answer exists.
    assert sources["wikipedia"] == []


async def test_wikipedia_is_only_asked_when_wikidata_misses(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    async def extract(name: str, language: str) -> str:
        sources["wikipedia"].append(name)
        return "The name derives from a Welsh well."

    monkeypatch.setattr(backends, "wikipedia_etymology", extract)
    place = await build_place(db, name="Ffynnongroyw", geonames_id=2_650_001, country_code="GB")
    place.wikidata_id = "Q7"

    enriched = await gazetteer.enrich(db, place.id)

    assert sources["wikidata"] == ["Q7"]
    assert enriched.etymology == "The name derives from a Welsh well."
    assert enriched.etymology_confidence == etymology.Confidence.HIGH
    assert enriched.etymology_source is not None
    assert "wikipedia.org" in enriched.etymology_source


async def test_the_article_is_read_in_the_readers_language_not_the_names(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    """A Turkish name's meaning still has to be explained in English.

    Reading tr.wikipedia for a Turkish place found nothing at all, because the
    section headings there are Turkish. The name's language belongs in the
    model prompt; the article language follows whoever is reading.
    """
    asked: list[str] = []

    async def record(name: str, language: str) -> None:
        asked.append(language)
        return None

    monkeypatch.setattr(backends, "wikipedia_etymology", record)
    place = await build_place(db, name="Batman", geonames_id=600_201, country_code="TR")

    await gazetteer.enrich(db, place.id)

    assert asked == [etymology.ARTICLE_LANGUAGE]
    assert etymology.ARTICLE_LANGUAGE == "en"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Grimsby", "farmstead"),
        ("Manchester", "Roman fort"),
        ("Llanfair", "church"),
        ("Kazakhstan", "land of"),
    ],
)
async def test_the_lexicon_reads_known_name_elements(
    db: AsyncSession, sources: dict[str, list[str]], name: str, expected: str
) -> None:
    """Rule-based, so it is medium confidence: right about the element, silent
    about whether that is the whole story for this particular place."""
    place = await build_place(db, name=name, geonames_id=hash(name) % 1_000_000, country_code="GB")

    enriched = await gazetteer.enrich(db, place.id)

    assert enriched.etymology is not None
    assert expected in enriched.etymology
    assert enriched.etymology_confidence == etymology.Confidence.MEDIUM
    assert enriched.etymology_source == etymology.LEXICON_SOURCE


async def test_the_model_is_last_and_its_answer_is_marked_unverified(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    client = with_llm(
        monkeypatch,
        FakeLLM({"known": True, "meaning": "Bright hollow.", "components": ["bright", "hollow"]}),
    )
    place = await build_place(db, name="Bolboda", geonames_id=600_101, country_code="RU")

    enriched = await gazetteer.enrich(db, place.id)

    assert len(client.prompts) == 1
    assert enriched.etymology == "Bright hollow."
    assert enriched.etymology_confidence == etymology.Confidence.UNVERIFIED
    assert enriched.etymology_source == "fake/model-1"


async def test_the_model_is_never_asked_without_a_known_language(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    """No language, no guess. A model asked to explain a name in a language
    nobody has established is being invited to invent one."""
    client = with_llm(monkeypatch, FakeLLM({"known": True, "meaning": "Anything at all."}))
    place = await build_place(db, name="Zzyzx", geonames_id=600_102, country_code=None)

    enriched = await gazetteer.enrich(db, place.id)

    assert client.prompts == []
    assert enriched.etymology is None
    assert enriched.etymology_confidence == etymology.Confidence.UNKNOWN


async def test_a_refusal_is_stored_as_an_answer_and_not_retried(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    """known: false is a success. Retrying until something comes back is how a
    system talks itself into a fabrication."""
    client = with_llm(monkeypatch, FakeLLM({"known": False, "meaning": None}))
    place = await build_place(db, name="Ubykh", geonames_id=600_103, country_code="RU")

    first = await gazetteer.enrich(db, place.id)
    assert first.etymology is None
    assert first.etymology_confidence == etymology.Confidence.UNKNOWN

    await gazetteer.enrich(db, place.id)

    assert len(client.prompts) == 1


async def test_a_resolved_etymology_is_never_looked_up_twice(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    async def named_after(wikidata_id: str) -> str:
        sources["wikidata"].append(wikidata_id)
        return "Named after a person."

    monkeypatch.setattr(backends, "wikidata_etymology", named_after)
    place = await build_place(db)
    place.wikidata_id = "Q42"

    await gazetteer.enrich(db, place.id)
    await gazetteer.enrich(db, place.id)

    assert sources["wikidata"] == ["Q42"]


async def test_every_source_failing_is_an_answer_rather_than_an_error(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    client = with_llm(monkeypatch, FakeLLM(None))
    place = await build_place(db, name="Qqqq", geonames_id=600_104, country_code="US")

    enriched = await gazetteer.enrich(db, place.id)

    assert enriched.etymology is None
    assert enriched.etymology_confidence == etymology.Confidence.UNKNOWN
    assert len(client.prompts) == 1


async def test_a_malformed_model_reply_is_treated_as_no_answer(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    """A shape we did not ask for is not evidence of anything."""
    with_llm(monkeypatch, FakeLLM({"meaning": 12, "known": "yes please"}))
    place = await build_place(db, name="Wwww", geonames_id=600_105, country_code="US")

    enriched = await gazetteer.enrich(db, place.id)

    assert enriched.etymology is None
    assert enriched.etymology_confidence == etymology.Confidence.UNKNOWN


async def test_the_prompt_carries_the_language_and_forbids_speculation(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sources: dict[str, list[str]]
) -> None:
    client = with_llm(monkeypatch, FakeLLM({"known": False}))
    place = await build_place(db, name="Bolboda", geonames_id=600_106, country_code="RU")

    await gazetteer.enrich(db, place.id)

    prompt = client.prompts[0]
    assert "Bolboda" in prompt
    assert "ru" in prompt
    assert "not confident" in prompt
