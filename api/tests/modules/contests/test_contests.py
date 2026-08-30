import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contest, Discovery, Nickname, NicknameHistory, Proposal, User
from app.modules import contests
from app.modules.contests import service
from app.modules.moderation import classifier
from tests.factories import build_place, build_user

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def accepting_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(_text: str) -> classifier.Categories:
        return classifier.Categories()

    monkeypatch.setattr(classifier, "classify", clean)
    classifier.breaker.reset()


Advance = Callable[..., None]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Advance:
    """A clock the test drives, so terms and windows can be stepped over."""
    current = {"now": NOW}

    def now() -> datetime:
        return current["now"]

    def advance(**delta: float) -> None:
        current["now"] = current["now"] + timedelta(**delta)

    monkeypatch.setattr(service, "_now", now)
    return advance


async def make_voter(session: AsyncSession, username: str, *, eligible: bool = True) -> User:
    """Voting needs an account at least 48h old with at least one discovery."""
    user = await build_user(session, username=username)
    user.created_at = NOW - timedelta(hours=72 if eligible else 1)
    if eligible:
        place = await build_place(
            session, name=f"{username} find", geonames_id=hash(username) % 100_000 + 200_000
        )
        session.add(Discovery(place_id=place.id, user_id=user.id, caption="found"))
    await session.flush()
    return user


async def test_the_first_proposal_opens_a_contest_closing_in_24h(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")

    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")

    contest = await db.get(Contest, proposal.contest_id)
    assert contest is not None
    assert contest.status == "open"
    assert contest.closes_at == NOW + timedelta(hours=24)


async def test_a_later_proposal_joins_the_open_contest(db: AsyncSession, clock: Advance) -> None:
    place = await build_place(db)
    first = await build_user(db, username="wit")
    second = await build_user(db, username="other")

    a = await contests.propose(db, place.id, first.id, "The Unfortunate Bay")
    b = await contests.propose(db, place.id, second.id, "Cape Embarrassment")

    assert a.contest_id == b.contest_id
    assert await db.scalar(select(func.count()).select_from(Contest)) == 1


async def test_moderation_runs_at_proposal_time(
    db: AsyncSession, clock: Advance, monkeypatch: pytest.MonkeyPatch
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")

    async def flags_spam(_text: str) -> classifier.Categories:
        return classifier.Categories(spam=True)

    monkeypatch.setattr(classifier, "classify", flags_spam)

    with pytest.raises(service.ProposalRejectedError):
        await contests.propose(db, place.id, author.id, "buy maps dot com")

    assert await db.scalar(select(func.count()).select_from(Proposal)) == 0


async def test_a_proposer_cannot_vote_for_their_own_proposal(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await make_voter(db, "wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")

    with pytest.raises(service.SelfVoteError):
        await contests.vote(db, proposal.id, author.id, 1)


async def test_voting_requires_a_settled_account_with_a_discovery(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    fresh = await make_voter(db, "fresh", eligible=False)

    with pytest.raises(service.NotEligibleToVoteError):
        await contests.vote(db, proposal.id, fresh.id, 1)


async def test_a_vote_can_be_changed_until_close_but_not_after(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    voter = await make_voter(db, "voter")

    await contests.vote(db, proposal.id, voter.id, 1)
    await contests.vote(db, proposal.id, voter.id, -1)
    await db.refresh(proposal)
    assert (proposal.agree, proposal.disagree) == (0, 1)

    clock(hours=25)
    with pytest.raises(service.ContestClosedError):
        await contests.vote(db, proposal.id, voter.id, 1)


async def test_resolve_due_promotes_a_winner_for_a_thirty_day_term(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    for index in range(16):
        voter = await make_voter(db, f"voter{index}")
        await contests.vote(db, proposal.id, voter.id, 1)

    clock(hours=25)
    outcomes = await contests.resolve_due(db)

    nickname = await db.get(Nickname, place.id)
    assert [outcome.kind for outcome in outcomes] == ["winner"]
    assert nickname is not None
    assert nickname.text == "The Unfortunate Bay"
    assert nickname.term_ends_at == NOW + timedelta(hours=25) + timedelta(days=30)


async def test_resolve_due_is_idempotent(db: AsyncSession, clock: Advance) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    for index in range(16):
        voter = await make_voter(db, f"voter{index}")
        await contests.vote(db, proposal.id, voter.id, 1)

    clock(hours=25)
    first = await contests.resolve_due(db)
    second = await contests.resolve_due(db)

    assert len(first) == 1
    assert second == []
    assert await db.scalar(select(func.count()).select_from(Nickname)) == 1
    assert await db.scalar(select(func.count()).select_from(NicknameHistory)) == 0


async def test_a_close_race_opens_a_runoff_between_the_top_two(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    a = await build_user(db, username="wit_a")
    b = await build_user(db, username="wit_b")
    c = await build_user(db, username="wit_c")
    first = await contests.propose(db, place.id, a.id, "The Unfortunate Bay")
    second = await contests.propose(db, place.id, b.id, "Cape Embarrassment")
    await contests.propose(db, place.id, c.id, "Regret Point")

    for index in range(16):
        voter = await make_voter(db, f"v{index}")
        await contests.vote(db, first.id, voter.id, 1)
        if index < 15:
            await contests.vote(db, second.id, voter.id, 1)

    clock(hours=25)
    outcomes = await contests.resolve_due(db)

    assert [outcome.kind for outcome in outcomes] == ["runoff"]
    runoff = (await db.execute(select(Contest).where(Contest.status == "runoff"))).scalars().one()
    assert runoff.closes_at == NOW + timedelta(hours=25) + timedelta(hours=24)
    entrants = (
        (await db.execute(select(Proposal).where(Proposal.contest_id == runoff.id))).scalars().all()
    )
    assert {entrant.text for entrant in entrants} == {
        "The Unfortunate Bay",
        "Cape Embarrassment",
    }
    assert all(entrant.agree == 0 for entrant in entrants)


async def test_no_quorum_leaves_a_leading_candidate_and_allows_a_reopen_after_seven_days(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    voter = await make_voter(db, "voter")
    await contests.vote(db, proposal.id, voter.id, 1)

    clock(hours=25)
    outcomes = await contests.resolve_due(db)

    assert [outcome.kind for outcome in outcomes] == ["no_quorum"]
    state = await contests.state_for(db, place.id)
    assert state.leading_candidate == "The Unfortunate Bay"
    assert state.nickname is None
    # Measured from when the contest closed, not when the scheduler got to it,
    # so scheduler lag cannot move the reopen date.
    assert state.reopens_at == NOW + timedelta(hours=24) + timedelta(days=7)


async def test_a_term_ending_with_no_challenger_renews_the_incumbent(
    db: AsyncSession, clock: Advance
) -> None:
    place = await build_place(db)
    author = await build_user(db, username="wit")
    proposal = await contests.propose(db, place.id, author.id, "The Unfortunate Bay")
    for index in range(16):
        voter = await make_voter(db, f"voter{index}")
        await contests.vote(db, proposal.id, voter.id, 1)

    clock(hours=25)
    await contests.resolve_due(db)
    promoted = await db.get(Nickname, place.id)
    assert promoted is not None
    first_term = promoted.term_ends_at

    clock(days=31)
    await contests.resolve_due(db)

    nickname = await db.get(Nickname, place.id)
    assert nickname is not None
    assert nickname.text == "The Unfortunate Bay"
    assert nickname.term_ends_at > first_term


def test_the_module_exposes_exactly_four_public_functions() -> None:
    public = [
        name
        for name, value in vars(contests).items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]

    assert sorted(public) == ["propose", "resolve_due", "state_for", "vote"]
