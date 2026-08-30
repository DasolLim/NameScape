"""Contest resolution. Pure functions: no database, no clock, no I/O.

Every rule in PRD 6.6 lives here, isolated from I/O so the boundaries can be
tested exactly. Comparisons are done in integers to avoid float drift at the
10% and 20% thresholds, where a rounding error would change the outcome.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

#: Net votes needed to resolve, by place tier.
QUORUM_BY_TIER: Final[dict[int, int]] = {1: 100, 2: 40, 3: 15}
DEFAULT_QUORUM: Final = 15

#: A proposal must be agreed with by at least this share of its voters.
RATIO_FLOOR_NUMERATOR: Final = 60
RATIO_FLOOR_DENOMINATOR: Final = 100

#: The winner must lead the runner-up by this much, or the top two run off.
MARGIN_NUMERATOR: Final = 11
MARGIN_DENOMINATOR: Final = 10

#: A challenger must beat the incumbent's original winning score by this much.
INCUMBENT_NUMERATOR: Final = 12
INCUMBENT_DENOMINATOR: Final = 10


@dataclass(frozen=True, slots=True)
class ProposalTally:
    id: int
    agree: int
    disagree: int
    created_at: datetime

    @property
    def score(self) -> int:
        return score(self.agree, self.disagree)


@dataclass(frozen=True, slots=True)
class Outcome:
    class Kind(StrEnum):
        WINNER = "winner"
        RUNOFF = "runoff"
        NO_QUORUM = "no_quorum"

    kind: "Outcome.Kind"
    winner_id: int | None = None
    winning_score: int | None = None
    runoff_ids: tuple[int, int] | None = None
    leader_id: int | None = None


def quorum_for(tier: int) -> int:
    return QUORUM_BY_TIER.get(tier, DEFAULT_QUORUM)


def score(agree: int, disagree: int) -> int:
    """Net votes. The only score in the system."""
    return agree - disagree


def meets_ratio_floor(agree: int, disagree: int) -> bool:
    """At least 60% agreement. No votes is not consent."""
    total = agree + disagree
    if total == 0:
        return False
    return agree * RATIO_FLOOR_DENOMINATOR >= RATIO_FLOOR_NUMERATOR * total


def _rank_key(proposal: ProposalTally) -> tuple[int, float, float]:
    """Score, then agree ratio, then earliest submission. All descending sorts."""
    total = proposal.agree + proposal.disagree
    ratio = proposal.agree / total if total else 0.0
    return (-proposal.score, -ratio, proposal.created_at.timestamp())


def resolve(
    proposals: list[ProposalTally],
    tier: int,
    incumbent: ProposalTally | None,
) -> Outcome:
    """Decide a contest. Total: never raises, for any input."""
    ranked = sorted(proposals, key=_rank_key)
    eligible = [p for p in ranked if meets_ratio_floor(p.agree, p.disagree)]

    def renew_or_no_quorum(leader: int | None) -> Outcome:
        if incumbent is not None:
            # No qualifying challenger: the incumbent renews silently.
            return Outcome(
                Outcome.Kind.WINNER, winner_id=incumbent.id, winning_score=incumbent.score
            )
        return Outcome(Outcome.Kind.NO_QUORUM, leader_id=leader)

    if not eligible:
        return renew_or_no_quorum(ranked[0].id if ranked else None)

    top = eligible[0]
    if top.score < quorum_for(tier):
        return renew_or_no_quorum(top.id)

    runner_up = eligible[1] if len(eligible) > 1 else None
    if runner_up is not None and (
        top.score * MARGIN_DENOMINATOR < runner_up.score * MARGIN_NUMERATOR
    ):
        return Outcome(Outcome.Kind.RUNOFF, runoff_ids=(top.id, runner_up.id))

    if incumbent is not None and (
        top.score * INCUMBENT_DENOMINATOR < incumbent.score * INCUMBENT_NUMERATOR
    ):
        return Outcome(
            Outcome.Kind.WINNER, winner_id=incumbent.id, winning_score=incumbent.score
        )

    return Outcome(Outcome.Kind.WINNER, winner_id=top.id, winning_score=top.score)
