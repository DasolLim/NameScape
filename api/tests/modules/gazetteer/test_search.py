import inspect
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import gazetteer
from app.modules.gazetteer import backends
from app.modules.gazetteer.importer import import_geonames
from tests.factories import build_discovery, build_place, build_user

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


async def test_a_prefix_ranks_the_prominent_place_first(db: AsyncSession) -> None:
    """Autocomplete: typing 'Lond' means London, not a village called Londa."""
    await build_place(db, name="Londa", geonames_id=700_101, country_code="IN", population=800)
    await build_place(
        db, name="London", geonames_id=700_102, country_code="GB", population=8_961_989
    )
    await build_place(db, name="Londe", geonames_id=700_103, country_code="ID", population=400)

    results = await gazetteer.search(db, "Lond")

    assert results[0].name == "London"


async def test_an_exact_match_survives_a_more_populous_prefix(db: AsyncSession) -> None:
    """Typing the whole of a small name should still find it."""
    await build_place(db, name="Dull", geonames_id=700_201, country_code="GB", population=84)
    await build_place(
        db, name="Dullstroom", geonames_id=700_202, country_code="ZA", population=1_200
    )

    results = await gazetteer.search(db, "Dull")

    assert results[0].name == "Dull"


async def test_a_populated_place_outranks_a_feature_of_the_same_name(
    db: AsyncSession,
) -> None:
    await build_place(
        db, name="Vancouver", geonames_id=700_301, country_code="CA", population=600_000
    )
    await build_place(
        db,
        name="Vancouver Bay",
        geonames_id=700_302,
        country_code="CA",
        feature_class="H",
        feature_code="BAY",
    )

    results = await gazetteer.search(db, "Vancou")

    assert results[0].name == "Vancouver"


async def test_search_returns_a_short_list_by_default(db: AsyncSession) -> None:
    """A suggestion list, not a result page."""
    for index in range(25):
        await build_place(db, name=f"Springfield {index}", geonames_id=700_400 + index)

    assert len(await gazetteer.search(db, "Springfield")) == gazetteer.DEFAULT_LIMIT
    assert gazetteer.DEFAULT_LIMIT <= 10


async def test_a_broad_search_finds_what_a_normal_one_misses(db: AsyncSession) -> None:
    """'Search worldwide' must do something, or it is a dead end with a button."""
    await build_place(db, name="Ffynnongroyw", geonames_id=700_501, country_code="GB")

    # Similarity 0.235: below pg_trgm's default 0.3, above the broad 0.12.
    typo = "Fynnogr"
    assert await gazetteer.search(db, typo) == []

    broadened = await gazetteer.search(db, typo, broad=True)

    assert [place.name for place in broadened] == ["Ffynnongroyw"]


async def test_results_carry_the_region_so_duplicates_are_distinguishable(
    db: AsyncSession,
) -> None:
    """Real gazetteer data has many places sharing a name; two identical rows
    tell the user nothing about which is which."""
    await build_place(db, name="Springfield", geonames_id=700_601, country_code="US")
    await db.execute(
        text("UPDATE places SET admin1 = 'IL' WHERE geonames_id = 700601"),
    )
    await build_place(db, name="Springfield", geonames_id=700_602, country_code="US")
    await db.execute(
        text("UPDATE places SET admin1 = 'MO' WHERE geonames_id = 700602"),
    )

    regions = {place.admin1 for place in await gazetteer.search(db, "Springfield")}

    assert regions == {"IL", "MO"}
