"""Contests: propose, vote, resolve, and read state.

The 24h window, moderation at submission, runoff scheduling, term tracking,
incumbent injection, nickname promotion and history writing all live here.
The rules themselves are in resolution.py, which has no I/O.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import observability
from app.models import Contest, Discovery, Nickname, NicknameHistory, Place, Proposal, User, Vote
from app.modules import moderation
from app.modules.contests import resolution
from app.modules.contests.resolution import Outcome, ProposalTally
from app.modules.moderation.normalize import normalize

CONTEST_WINDOW: Final = timedelta(hours=24)
RUNOFF_WINDOW: Final = timedelta(hours=24)
TERM: Final = timedelta(days=30)
REOPEN_AFTER: Final = timedelta(days=7)

#: Sockpuppet defence: an account must have settled and contributed once.
MIN_ACCOUNT_AGE: Final = timedelta(hours=48)

_LIVE_STATUSES: Final = ("open", "runoff")


class ProposalRejectedError(Exception):
    """Moderation refused the text. Carries no reason by design."""


class SelfVoteError(Exception):
    """A proposer cannot vote for their own proposal."""


class NotEligibleToVoteError(Exception):
    """The account is too new, or has never discovered anything."""


class ContestClosedError(Exception):
    """The window has passed; votes are final."""


@dataclass(frozen=True, slots=True)
class ContestOutcome:
    place_id: int
    contest_id: int
    kind: str
    winner_id: int | None = None


@dataclass(frozen=True, slots=True)
class ProposalState:
    id: int
    text: str
    agree: int
    disagree: int
    score: int
    is_incumbent: bool


@dataclass(frozen=True, slots=True)
class ContestState:
    place_id: int
    nickname: str | None
    leading_candidate: str | None
    closes_at: datetime | None
    reopens_at: datetime | None
    quorum: int
    proposals: list[ProposalState]


def _now() -> datetime:
    """Indirected so tests can drive the clock without sleeping."""
    return datetime.now(UTC)


async def _live_contest(session: AsyncSession, place_id: int) -> Contest | None:
    return (
        (
            await session.execute(
                select(Contest)
                .where(Contest.place_id == place_id, Contest.status.in_(_LIVE_STATUSES))
                .order_by(Contest.id.desc())
            )
        )
        .scalars()
        .first()
    )


async def propose(session: AsyncSession, place_id: int, user_id: UUID, text: str) -> Proposal:
    """Put a nickname forward, opening a contest if this is the first."""
    screened = await moderation.screen(
        session, text, moderation.ScreenContext(place_id=place_id, kind="proposal")
    )
    if screened.verdict is moderation.Verdict.REJECT:
        raise ProposalRejectedError
    if screened.verdict is moderation.Verdict.DUPLICATE and screened.duplicate_of is not None:
        existing = await session.get(Proposal, screened.duplicate_of)
        if existing is not None:
            return existing

    contest = await _live_contest(session, place_id)
    if contest is None:
        contest = Contest(
            place_id=place_id, status="open", opened_at=_now(), closes_at=_now() + CONTEST_WINDOW
        )
        session.add(contest)
        await session.flush()

    proposal = Proposal(
        contest_id=contest.id,
        place_id=place_id,
        user_id=user_id,
        text=text,
        normalized_text=normalize(text),
        agree=0,
        disagree=0,
        is_incumbent=False,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def _may_vote(session: AsyncSession, user_id: UUID) -> bool:
    user = await session.get(User, user_id)
    if user is None or user.created_at is None:
        return False
    if _now() - user.created_at < MIN_ACCOUNT_AGE:
        return False
    found = await session.scalar(
        select(func.count()).select_from(Discovery).where(Discovery.user_id == user_id)
    )
    return bool(found)


async def vote(session: AsyncSession, proposal_id: int, user_id: UUID, value: int) -> None:
    """Agree or disagree. Changeable until the contest closes, never after."""
    proposal = await session.get(Proposal, proposal_id)
    if proposal is None:
        raise ContestClosedError

    contest = await session.get(Contest, proposal.contest_id) if proposal.contest_id else None
    if contest is None or contest.status not in _LIVE_STATUSES or contest.closes_at <= _now():
        raise ContestClosedError
    if proposal.user_id == user_id:
        raise SelfVoteError
    if not await _may_vote(session, user_id):
        raise NotEligibleToVoteError

    direction = 1 if value > 0 else -1
    existing = await session.get(Vote, {"user_id": user_id, "proposal_id": proposal_id})
    if existing is not None:
        if existing.value == direction:
            return
        # Undo the old vote before applying the new one.
        if existing.value > 0:
            proposal.agree -= 1
        else:
            proposal.disagree -= 1
        existing.value = direction
    else:
        session.add(Vote(user_id=user_id, proposal_id=proposal_id, value=direction))

    if direction > 0:
        proposal.agree += 1
    else:
        proposal.disagree += 1
    await session.flush()


async def _tallies(session: AsyncSession, contest_id: int) -> list[ProposalTally]:
    proposals = (
        (await session.execute(select(Proposal).where(Proposal.contest_id == contest_id)))
        .scalars()
        .all()
    )
    return [
        ProposalTally(
            id=p.id, agree=p.agree, disagree=p.disagree, created_at=p.created_at or _now()
        )
        for p in proposals
    ]


async def _promote(
    session: AsyncSession, contest: Contest, proposal_id: int, score: int, at: datetime
) -> None:
    proposal = await session.get(Proposal, proposal_id)
    if proposal is None:
        return

    previous = await session.get(Nickname, contest.place_id)
    if previous is not None and previous.text != proposal.text:
        session.add(
            NicknameHistory(
                place_id=contest.place_id,
                text=previous.text,
                held_from=previous.created_at or at,
                held_until=at,
            )
        )
    if previous is not None:
        await session.delete(previous)
        await session.flush()

    session.add(
        Nickname(
            place_id=contest.place_id,
            text=proposal.text,
            proposal_id=proposal.id,
            score=score,
            term_ends_at=at + TERM,
            created_at=at,
        )
    )
    contest.status = "resolved"
    contest.winner_proposal_id = proposal.id
    contest.winning_score = score
    contest.term_ends_at = at + TERM


async def _open_runoff(
    session: AsyncSession, contest: Contest, entrants: tuple[int, int], at: datetime
) -> None:
    contest.status = "expired"
    runoff = Contest(
        place_id=contest.place_id, status="runoff", opened_at=at, closes_at=at + RUNOFF_WINDOW
    )
    session.add(runoff)
    await session.flush()

    for proposal_id in entrants:
        original = await session.get(Proposal, proposal_id)
        if original is None:
            continue
        # Fresh rows: a runoff is a new vote, not a continuation of the old one.
        session.add(
            Proposal(
                contest_id=runoff.id,
                place_id=original.place_id,
                user_id=original.user_id,
                text=original.text,
                normalized_text=original.normalized_text,
                agree=0,
                disagree=0,
                is_incumbent=original.is_incumbent,
            )
        )
    await session.flush()


async def resolve_due(session: AsyncSession) -> list[ContestOutcome]:
    """Close every contest and term that is due. Safe to run twice."""
    at = _now()
    outcomes: list[ContestOutcome] = []

    due = (
        (
            await session.execute(
                select(Contest).where(Contest.status.in_(_LIVE_STATUSES), Contest.closes_at <= at)
            )
        )
        .scalars()
        .all()
    )

    for contest in due:
        place = await session.get(Place, contest.place_id)
        tier = place.tier if place is not None else 3
        current = await session.get(Nickname, contest.place_id)
        incumbent = (
            ProposalTally(id=current.proposal_id, agree=current.score, disagree=0, created_at=at)
            if current is not None
            else None
        )

        outcome = resolution.resolve(await _tallies(session, contest.id), tier, incumbent)

        if outcome.kind is Outcome.Kind.WINNER and outcome.winner_id is not None:
            await _promote(session, contest, outcome.winner_id, outcome.winning_score or 0, at)
        elif outcome.kind is Outcome.Kind.RUNOFF and outcome.runoff_ids is not None:
            await _open_runoff(session, contest, outcome.runoff_ids, at)
        else:
            contest.status = "expired"

        outcomes.append(
            ContestOutcome(
                place_id=contest.place_id,
                contest_id=contest.id,
                kind=outcome.kind.value,
                winner_id=outcome.winner_id,
            )
        )

    observability.contests_resolved_total.inc(len(outcomes))
    outcomes.extend(await _renew_expired_terms(session, at))
    await session.flush()
    return outcomes


async def _renew_expired_terms(session: AsyncSession, at: datetime) -> list[ContestOutcome]:
    """A term ending with nobody contesting it renews silently."""
    renewed: list[ContestOutcome] = []
    expiring = (
        (await session.execute(select(Nickname).where(Nickname.term_ends_at <= at))).scalars().all()
    )

    for nickname in expiring:
        if await _live_contest(session, nickname.place_id) is not None:
            continue
        nickname.term_ends_at = at + TERM
        renewed.append(
            ContestOutcome(
                place_id=nickname.place_id,
                contest_id=0,
                kind="renewed",
                winner_id=nickname.proposal_id,
            )
        )
    return renewed


async def state_for(session: AsyncSession, place_id: int) -> ContestState:
    """Everything the place sheet needs to draw the contest board."""
    place = await session.get(Place, place_id)
    nickname = await session.get(Nickname, place_id)
    contest = await _live_contest(session, place_id)

    latest = (
        (
            await session.execute(
                select(Contest).where(Contest.place_id == place_id).order_by(Contest.id.desc())
            )
        )
        .scalars()
        .first()
    )

    source_contest = contest or latest
    proposals: list[ProposalState] = []
    if source_contest is not None:
        rows = (
            (
                await session.execute(
                    select(Proposal)
                    .where(Proposal.contest_id == source_contest.id)
                    .order_by((Proposal.agree - Proposal.disagree).desc(), Proposal.id)
                )
            )
            .scalars()
            .all()
        )
        proposals = [
            ProposalState(
                id=p.id,
                text=p.text,
                agree=p.agree,
                disagree=p.disagree,
                score=p.agree - p.disagree,
                is_incumbent=p.is_incumbent,
            )
            for p in rows
        ]

    leading = proposals[0].text if proposals and nickname is None else None
    reopens_at = (
        latest.closes_at + REOPEN_AFTER
        if contest is None and latest is not None and nickname is None
        else None
    )

    return ContestState(
        place_id=place_id,
        nickname=nickname.text if nickname else None,
        leading_candidate=leading,
        closes_at=contest.closes_at if contest else None,
        reopens_at=reopens_at,
        quorum=resolution.quorum_for(place.tier if place else 3),
        proposals=proposals,
    )
