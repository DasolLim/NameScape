"""Drafting the daily puzzle, offline and in batches.

The first clue says what the name means without saying the name, which is the
one part a model is genuinely good at and the one part it can ruin. A leaked
name makes the puzzle trivial, so the model's own opinion of whether it leaked
is treated as a hint and checked deterministically afterwards.

Nothing here runs while a player waits. Every test mocks the model entirely.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Puzzle
from app.modules.gazetteer.etymology import Confidence
from app.modules.puzzles import generation
from tests.factories import build_place

TOMORROW = date(2026, 9, 1)


class FakeLLM:
    """Replies in order, so a retry can be given something different."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "fake/model-1"

    async def complete_json(self, prompt: str, *, system: str | None = None) -> Any:
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else None


async def puzzle_place(
    db: AsyncSession,
    *,
    name: str = "Ffynnongroyw",
    geonames_id: int = 2_650_100,
    country_code: str | None = "GB",
    tier: int = 2,
    etymology: str | None = "The name derives from the Welsh for clear well.",
    lon: float = -3.3167,
    lat: float = 53.3417,
) -> Any:
    place = await build_place(
        db,
        name=name,
        geonames_id=geonames_id,
        country_code=country_code,
        tier=tier,
        lon=lon,
        lat=lat,
    )
    place.etymology = etymology
    place.etymology_confidence = Confidence.HIGH if etymology else None
    await db.flush()
    return place


async def test_a_place_with_no_etymology_is_not_puzzle_material(db: AsyncSession) -> None:
    """The first clue is the meaning of the name. With no meaning there is no
    puzzle, only five guesses at nothing."""
    await puzzle_place(db, etymology=None)

    assert await generation.candidates(db, limit=5) == []


async def test_tier_three_places_are_excluded(db: AsyncSession) -> None:
    """Tier drives quorum elsewhere; here it stands in for whether anyone has
    a chance of guessing the place at all."""
    await puzzle_place(db, tier=3)

    assert await generation.candidates(db, limit=5) == []


async def test_a_place_inside_a_restricted_zone_is_excluded(db: AsyncSession) -> None:
    await puzzle_place(db)
    await db.execute(
        text(
            "INSERT INTO restricted_zones (geom, rule_type, reason, source) VALUES "
            "(ST_GeogFromText('SRID=4326;POLYGON((-3.4 53.3,-3.2 53.3,"
            "-3.2 53.4,-3.4 53.4,-3.4 53.3))'), 'no_nomination', 'A memorial.', 'test')"
        )
    )

    assert await generation.candidates(db, limit=5) == []


async def test_a_place_with_no_continent_is_excluded(db: AsyncSession) -> None:
    """Two of the five clues are the continent and the country. Without a
    country there are only three clues, and the puzzle is not fair."""
    await puzzle_place(db, country_code=None)

    assert await generation.candidates(db, limit=5) == []


async def test_a_place_already_used_is_never_the_answer_twice(db: AsyncSession) -> None:
    place = await puzzle_place(db)
    db.add(
        Puzzle(
            puzzle_date=date(2026, 1, 1),
            place_id=place.id,
            clues=["something"],
            status="approved",
            generated_by="fake/model-1",
        )
    )
    await db.flush()

    assert await generation.candidates(db, limit=5) == []


async def test_an_etymology_that_states_no_meaning_is_not_puzzle_material(
    db: AsyncSession,
) -> None:
    """Real output: Ankara's resolved etymology is "The orthography of the name
    has varied over the ages", which is true, cited, and says nothing about what
    the name means. Handing that to a model as the basis for a meaning clue is
    asking it to invent one.
    """
    await puzzle_place(db, etymology="The orthography of the name has varied over the ages.")

    assert await generation.candidates(db, limit=5) == []


async def test_an_etymology_that_states_a_meaning_qualifies(db: AsyncSession) -> None:
    for index, etymology in enumerate(
        [
            "The name derives from the Old English.",
            "It means clear well.",
            "Named after a family of settlers.",
            "The name comes from a word for a river mouth.",
        ]
    ):
        await puzzle_place(
            db, name=f"Placeby {index}", geonames_id=710_000 + index, etymology=etymology
        )

    assert len(await generation.candidates(db, limit=10)) == 4


async def test_a_good_candidate_is_offered(db: AsyncSession) -> None:
    place = await puzzle_place(db)

    found = await generation.candidates(db, limit=5)

    assert [candidate.id for candidate in found] == [place.id]


async def test_usable_candidates_are_found_behind_unusable_ones(db: AsyncSession) -> None:
    """The gate runs in Python, so a plain SQL LIMIT would hand back three rows,
    discard two of them, and leave a ninety day batch short of days.
    """
    for index in range(8):
        await puzzle_place(
            db,
            name=f"Dudby {index}",
            geonames_id=720_000 + index,
            # High population, so these sort first and crowd out the good ones.
            etymology="The orthography of the name has varied over the ages.",
        )
    for index in range(3):
        await puzzle_place(
            db,
            name=f"Goodby {index}",
            geonames_id=730_000 + index,
            etymology="The name derives from a word for a clearing.",
        )

    found = await generation.candidates(db, limit=3)

    assert len(found) == 3
    assert all(place.name.startswith("Goodby") for place in found)


async def test_a_clue_that_names_the_place_is_rejected(db: AsyncSession) -> None:
    """The main quality risk in the whole feature."""
    place = await puzzle_place(db)

    assert generation.leaks("A clear well, in Ffynnongroyw.", place) is True
    # Any part of it, not only the whole thing.
    assert generation.leaks("Something to do with a groyw.", place) is True
    # Case and spacing are not a defence.
    assert generation.leaks("ffynnon groyw means clear well", place) is True
    assert generation.leaks("A well of fresh water in a Welsh village.", place) is False


async def test_an_alternate_name_counts_as_a_leak(db: AsyncSession) -> None:
    place = await puzzle_place(db)
    place.alternate_names = ["Ffynnon Groyw", "Ффиннонгройв"]
    await db.flush()

    assert generation.leaks("Also written Ффиннонгройв.", place) is True


async def test_a_leaking_clue_is_regenerated_rather_than_stored(db: AsyncSession) -> None:
    """And the model's own leaks_name is not what catches it."""
    place = await puzzle_place(db)
    client = FakeLLM(
        {"clue": "The clear well at Ffynnongroyw.", "leaks_name": False},
        {"clue": "A well of notably fresh water.", "leaks_name": False},
    )

    drafted = await generation.draft(client, place)

    assert drafted == "A well of notably fresh water."
    assert len(client.prompts) == 2


async def test_a_model_that_keeps_leaking_fails_rather_than_writing_a_bad_row(
    db: AsyncSession,
) -> None:
    place = await puzzle_place(db)
    leak = {"clue": "It is Ffynnongroyw.", "leaks_name": False}
    client = FakeLLM(leak, leak, leak, leak)

    with pytest.raises(generation.GenerationError):
        await generation.draft(client, place)


async def test_malformed_json_is_retried_and_then_gives_up(db: AsyncSession) -> None:
    place = await puzzle_place(db)
    client = FakeLLM(None, {"clue": "A well of fresh water."})

    assert await generation.draft(client, place) == "A well of fresh water."

    hopeless = FakeLLM(None, None, None, None)
    with pytest.raises(generation.GenerationError):
        await generation.draft(hopeless, place)


async def test_a_model_admitting_the_leak_is_believed_immediately(db: AsyncSession) -> None:
    """Its self-report is worth something as a hint. It is just never the only
    check, because a model that leaks the name tends not to notice."""
    place = await puzzle_place(db)
    client = FakeLLM(
        {"clue": "A perfectly innocent clue.", "leaks_name": True},
        {"clue": "A well of fresh water.", "leaks_name": False},
    )

    assert await generation.draft(client, place) == "A well of fresh water."


async def test_a_generated_puzzle_is_written_as_a_draft(db: AsyncSession) -> None:
    place = await puzzle_place(db)
    client = FakeLLM({"clue": "A well of fresh water.", "leaks_name": False})

    written = await generation.generate(db, client, TOMORROW, limit=1)

    assert written == 1
    puzzle = (await db.execute(select(Puzzle))).scalars().one()
    assert puzzle.puzzle_date == TOMORROW
    assert puzzle.place_id == place.id
    # Never live, never even approved: a person decides, months ahead.
    assert puzzle.status == "draft"
    assert puzzle.approved_by is None
    assert puzzle.generated_by == "fake/model-1"


async def test_the_clues_run_from_meaning_to_country(db: AsyncSession) -> None:
    await puzzle_place(db)
    client = FakeLLM({"clue": "A well of fresh water.", "leaks_name": False})

    await generation.generate(db, client, TOMORROW, limit=1)

    clues = (await db.execute(select(Puzzle))).scalars().one().clues
    assert clues[0] == "A well of fresh water."
    # Feature type and rough scale, then continent, then country.
    assert "populated place" in clues[1].casefold()
    assert clues[2] == "Europe"
    assert clues[3] == "United Kingdom"
    # The fifth reveal is the pin, which is the place itself rather than prose.
    assert len(clues) == 4


async def test_no_clue_names_the_place(db: AsyncSession) -> None:
    """Belt and braces: the derived clues are ours, but they are still checked,
    because a country called Djibouti is also a city called Djibouti."""
    await puzzle_place(db, name="Djibouti", geonames_id=223_817, country_code="DJ")
    client = FakeLLM({"clue": "A place of the boiling pot.", "leaks_name": False})

    with pytest.raises(generation.GenerationError):
        await generation.generate(db, client, TOMORROW, limit=1)


async def test_the_same_date_never_generates_twice(db: AsyncSession) -> None:
    await puzzle_place(db)
    await puzzle_place(db, name="Grimsby", geonames_id=2_648_101)
    client = FakeLLM(
        {"clue": "A well of fresh water.", "leaks_name": False},
        {"clue": "A farmstead of a man called Grim.", "leaks_name": False},
    )

    first = await generation.generate(db, client, TOMORROW, limit=1)
    second = await generation.generate(db, client, TOMORROW, limit=1)

    assert first == 1
    assert second == 0
    assert len((await db.execute(select(Puzzle))).scalars().all()) == 1


async def test_a_batch_fills_consecutive_days(db: AsyncSession) -> None:
    for index in range(3):
        await puzzle_place(db, name=f"Placeby {index}", geonames_id=700_000 + index)
    client = FakeLLM(*({"clue": f"A clue {n}.", "leaks_name": False} for n in range(3)))

    written = await generation.generate(db, client, TOMORROW, limit=3)

    assert written == 3
    dates = sorted(
        puzzle.puzzle_date for puzzle in (await db.execute(select(Puzzle))).scalars().all()
    )
    assert dates == [TOMORROW + timedelta(days=offset) for offset in range(3)]
