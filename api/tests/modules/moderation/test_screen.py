import inspect

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import moderation
from app.modules.moderation import classifier, service

CLEAN = "A town whose name is funnier than anything we could invent."


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: the classifier is reachable and finds nothing. Breaker reset."""

    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


@pytest.fixture
def context() -> service.ScreenContext:
    return service.ScreenContext(place_id=1, kind="proposal")


async def test_clean_text_is_accepted(db: AsyncSession, context: service.ScreenContext) -> None:
    result = await moderation.screen(db, CLEAN, context)

    assert result.verdict is service.Verdict.ACCEPT


async def test_zero_width_and_homoglyph_evasion_is_normalised_before_matching(
    db: AsyncSession, context: service.ScreenContext
) -> None:
    zero_width = "bad\u200bword"
    homoglyph = "b\u0430dword"  # Cyrillic а in place of Latin a

    assert (await moderation.screen(db, zero_width, context)).verdict is service.Verdict.REJECT
    assert (await moderation.screen(db, homoglyph, context)).verdict is service.Verdict.REJECT


async def test_leetspeak_evasion_is_caught_by_the_blocklist(
    db: AsyncSession, context: service.ScreenContext
) -> None:
    result = await moderation.screen(db, "b4dw0rd", context)

    assert result.verdict is service.Verdict.REJECT


async def test_any_positive_category_rejects(
    db: AsyncSession, context: service.ScreenContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def flags_violence(_text: str) -> classifier.Categories:
        return classifier.Categories(violent=True)

    monkeypatch.setattr(classifier, "classify", flags_violence)

    assert (await moderation.screen(db, CLEAN, context)).verdict is service.Verdict.REJECT


async def test_a_classifier_timeout_rejects_and_never_admits(
    db: AsyncSession, context: service.ScreenContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed. This is the test that matters most in the module."""

    async def times_out(_text: str) -> classifier.Categories:
        raise TimeoutError("classifier did not answer")

    monkeypatch.setattr(classifier, "classify", times_out)

    assert (await moderation.screen(db, CLEAN, context)).verdict is service.Verdict.REJECT


async def test_five_consecutive_failures_trip_the_circuit_breaker(
    db: AsyncSession, context: service.ScreenContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def always_fails(_text: str) -> classifier.Categories:
        nonlocal calls
        calls += 1
        raise TimeoutError("down")

    monkeypatch.setattr(classifier, "classify", always_fails)

    for _ in range(6):
        assert (await moderation.screen(db, CLEAN, context)).verdict is service.Verdict.REJECT

    # Once open, the breaker stops spending calls on a dead dependency.
    assert calls == classifier.FAILURE_THRESHOLD


async def test_a_near_duplicate_merges_rather_than_rejects(db: AsyncSession) -> None:
    from tests.factories import build_place, build_proposal, build_user

    place = await build_place(db)
    author = await build_user(db, username="wit")
    existing = await build_proposal(
        db, place_id=place.id, user_id=author.id, text="The Town That Shall Not Be Named"
    )
    context = service.ScreenContext(place_id=place.id, kind="proposal")

    result = await moderation.screen(db, "the town that shall not be named!", context)

    assert result.verdict is service.Verdict.DUPLICATE
    assert result.duplicate_of == existing.id


async def test_the_result_never_carries_a_rejection_reason(
    db: AsyncSession, context: service.ScreenContext
) -> None:
    result = await moderation.screen(db, "b4dw0rd", context)

    assert "reason" not in set(vars(type(result)).get("__annotations__", {}))
    assert not any("reason" in str(value).lower() for value in vars(result).values())


def test_the_module_exposes_exactly_one_public_function() -> None:
    public = [
        name
        for name, value in vars(moderation).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert public == ["screen"]
