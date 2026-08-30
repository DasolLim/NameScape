"""Every rule in PRD 6.6, with the boundaries stated explicitly.

Pure functions only: no database, no clock, no I/O.
"""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.contests import resolution
from app.modules.contests.resolution import Outcome, ProposalTally

EPOCH = datetime(2026, 8, 1, tzinfo=UTC)


def tally(id: int, agree: int, disagree: int = 0, minutes: int = 0) -> ProposalTally:
    return ProposalTally(
        id=id, agree=agree, disagree=disagree, created_at=EPOCH + timedelta(minutes=minutes)
    )


@pytest.mark.parametrize(("tier", "expected"), [(1, 100), (2, 40), (3, 15)])
def test_quorum_scales_by_tier(tier: int, expected: int) -> None:
    assert resolution.quorum_for(tier) == expected


def test_score_is_net_votes() -> None:
    assert resolution.score(120, 5) == 115
    assert resolution.score(0, 7) == -7


@pytest.mark.parametrize(
    ("agree", "disagree", "passes"),
    [
        (60, 40, True),  # exactly 60% clears the floor
        (59, 41, False),
        (100, 0, True),
        (0, 0, False),  # no votes is not consent
    ],
)
def test_the_agree_ratio_floor(agree: int, disagree: int, passes: bool) -> None:
    assert resolution.meets_ratio_floor(agree, disagree) is passes


def test_a_proposal_below_the_ratio_floor_cannot_win_on_net_votes_alone() -> None:
    divisive = tally(1, agree=150, disagree=400)
    liked = tally(2, agree=120, disagree=5)

    outcome = resolution.resolve([divisive, liked], tier=3, incumbent=None)

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 2


def test_a_single_proposal_meeting_quorum_wins_outright() -> None:
    outcome = resolution.resolve([tally(1, agree=20, disagree=2)], tier=3, incumbent=None)

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 1
    assert outcome.winning_score == 18


def test_below_quorum_names_a_leading_candidate_instead_of_a_winner() -> None:
    outcome = resolution.resolve([tally(1, agree=10), tally(2, agree=4)], tier=3, incumbent=None)

    assert outcome.kind is Outcome.Kind.NO_QUORUM
    assert outcome.leader_id == 1


def test_a_margin_under_ten_percent_goes_to_a_runoff() -> None:
    outcome = resolution.resolve(
        [tally(1, agree=20), tally(2, agree=19)], tier=3, incumbent=None
    )

    assert outcome.kind is Outcome.Kind.RUNOFF
    assert outcome.runoff_ids == (1, 2)


def test_a_margin_of_exactly_ten_percent_is_a_win_not_a_runoff() -> None:
    """Boundary: 22 leads 20 by exactly 10%."""
    outcome = resolution.resolve(
        [tally(1, agree=22), tally(2, agree=20)], tier=3, incumbent=None
    )

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 1


def test_an_incumbent_survives_a_challenger_that_does_not_beat_it_by_twenty_percent() -> None:
    outcome = resolution.resolve(
        [tally(1, agree=23)], tier=3, incumbent=tally(99, agree=20)
    )

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 99
    assert outcome.winning_score == 20


def test_a_challenger_exactly_twenty_percent_above_the_incumbent_unseats_it() -> None:
    """Boundary: 24 is exactly 20% above 20."""
    outcome = resolution.resolve(
        [tally(1, agree=24)], tier=3, incumbent=tally(99, agree=20)
    )

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 1


def test_no_challenger_renews_the_incumbent_silently() -> None:
    outcome = resolution.resolve([], tier=3, incumbent=tally(99, agree=40))

    assert outcome.kind is Outcome.Kind.WINNER
    assert outcome.winner_id == 99


def test_an_empty_proposal_list_produces_no_quorum_without_raising() -> None:
    outcome = resolution.resolve([], tier=1, incumbent=None)

    assert outcome.kind is Outcome.Kind.NO_QUORUM
    assert outcome.leader_id is None


def test_a_tie_breaks_on_agree_ratio_then_on_earlier_submission() -> None:
    # Both net 20; the second has the cleaner ratio.
    noisy = tally(1, agree=40, disagree=20, minutes=0)
    clean = tally(2, agree=25, disagree=5, minutes=10)

    outcome = resolution.resolve([noisy, clean], tier=3, incumbent=None)

    assert outcome.kind is Outcome.Kind.RUNOFF
    assert outcome.runoff_ids == (2, 1)

    # Identical ratios: the earlier submission leads.
    first = tally(3, agree=25, disagree=5, minutes=0)
    second = tally(4, agree=25, disagree=5, minutes=30)

    tied = resolution.resolve([second, first], tier=3, incumbent=None)

    assert tied.runoff_ids == (3, 4)


@given(
    proposals=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=999),
            st.integers(min_value=0, max_value=5_000),
            st.integers(min_value=0, max_value=5_000),
        ),
        max_size=12,
    ),
    tier=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=300)
def test_resolve_is_total_and_deterministic(
    proposals: list[tuple[int, int, int]], tier: int
) -> None:
    """It never raises, and the same input always gives the same answer."""
    tallies = [
        ProposalTally(id=id, agree=agree, disagree=disagree, created_at=EPOCH)
        for id, agree, disagree in proposals
    ]

    first = resolution.resolve(tallies, tier=tier, incumbent=None)
    second = resolution.resolve(tallies, tier=tier, incumbent=None)

    assert first == second
    assert first.kind in set(Outcome.Kind)


def test_the_resolution_module_performs_no_io() -> None:
    """Isolating the rules from I/O is what makes these boundaries testable."""
    import ast
    import pathlib

    source = pathlib.Path(resolution.__file__).read_text(encoding="utf-8")
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {"dataclasses", "datetime", "enum", "typing"}
