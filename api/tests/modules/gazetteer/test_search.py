import inspect
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import gazetteer
from app.modules.gazetteer import backends
from app.modules.gazetteer.importer import import_geonames
from tests.factories import build_discovery, build_user

FIXTURE = Path(__file__).parents[2] / "fixtures" / "geonames_sample.txt"


@pytest.fixture(autouse=True)
async def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every backend is off by default; each test opts into what it needs."""

    async def index_unavailable(*_args: object, **_kwargs: object) -> None:
        return None

    async def no_photon_hits(*_args: object, **_kwargs: object) -> list[int]:
        return []

    async def no_wikidata(*_args: object, **_kwargs: object) -> str | None:
        return None

    monkeypatch.setattr(backends, "typesense_ids", index_unavailable)
    monkeypatch.setattr(backends, "photon_ids", no_photon_hits)
    monkeypatch.setattr(backends, "wikidata_etymology", no_wikidata)


async def test_an_empty_query_returns_no_results_rather_than_an_error(db: AsyncSession) -> None:
    assert await gazetteer.search(db, "   ") == []


async def test_exact_name_matches_rank_above_alternate_name_matches(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    results = await gazetteer.search(db, "Piddle")

    assert results[0].name == "River Piddle"


async def test_alternate_names_are_searchable(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    results = await gazetteer.search(db, "Krung Thep")

    assert [r.name for r in results] == ["Bangkok"]


async def test_a_typo_falls_through_to_the_fuzzy_backend(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await import_geonames(db, FIXTURE)

    async def photon_finds_dildo(*_args: object, **_kwargs: object) -> list[int]:
        return [6942553]

    monkeypatch.setattr(backends, "photon_ids", photon_finds_dildo)

    results = await gazetteer.search(db, "Dildoo")

    assert [r.name for r in results] == ["Dildo"]


async def test_search_respects_a_country_filter(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)

    everywhere = await gazetteer.search(db, "Hell")
    norway_only = await gazetteer.search(db, "Hell", country_code="NO")

    assert len(everywhere) == 2
    assert [r.country_code for r in norway_only] == ["NO"]


async def test_results_carry_claim_status(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)
    finder = await build_user(db, username="cartographer")
    dildo = await gazetteer.resolve(db, 6942553)
    assert dildo is not None
    await build_discovery(db, place_id=dildo.id, user_id=finder.id)

    claimed = (await gazetteer.search(db, "Dildo"))[0]
    unclaimed = (await gazetteer.search(db, "Boring"))[0]

    assert claimed.claimed_by == "cartographer"
    assert unclaimed.claimed_by is None


async def test_resolve_returns_none_for_an_unknown_id(db: AsyncSession) -> None:
    assert await gazetteer.resolve(db, 999_999_999) is None


async def test_enrich_stores_etymology_and_does_not_ask_twice(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await import_geonames(db, FIXTURE)
    dildo = await gazetteer.resolve(db, 6942553)
    assert dildo is not None
    dildo.wikidata_id = "Q1189712"

    calls = 0

    async def wikidata(*_args: object, **_kwargs: object) -> str | None:
        nonlocal calls
        calls += 1
        return "Probably from a Newfoundland shipbuilding pin."

    monkeypatch.setattr(backends, "wikidata_etymology", wikidata)

    first = await gazetteer.enrich(db, dildo.id)
    second = await gazetteer.enrich(db, dildo.id)

    assert first.etymology == "Probably from a Newfoundland shipbuilding pin."
    assert second.etymology == first.etymology
    assert calls == 1


async def test_enrich_degrades_when_wikidata_has_nothing(db: AsyncSession) -> None:
    await import_geonames(db, FIXTURE)
    boring = await gazetteer.search(db, "Boring")

    enriched = await gazetteer.enrich(db, boring[0].id)

    assert enriched.etymology is None


def test_the_module_exposes_exactly_three_public_functions() -> None:
    public = [
        name
        for name, value in vars(gazetteer).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["enrich", "resolve", "search"]
