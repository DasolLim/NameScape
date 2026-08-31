from datetime import date

import pytest

from app.modules.accounts import streak


def d(day: int) -> date:
    return date(2026, 8, day)


TODAY = d(30)


def test_activity_today_starts_a_streak_of_one() -> None:
    assert streak.length({d(30)}, today=TODAY) == 1


def test_consecutive_days_accumulate() -> None:
    assert streak.length({d(28), d(29), d(30)}, today=TODAY) == 3


def test_a_streak_ending_yesterday_is_still_alive() -> None:
    """The day is not over. Breaking it at midnight would be punitive."""
    assert streak.length({d(27), d(28), d(29)}, today=TODAY) == 3


def test_a_gap_of_two_days_breaks_it() -> None:
    assert streak.length({d(26), d(27), d(28)}, today=TODAY) == 0


def test_a_gap_inside_the_run_only_counts_the_recent_part() -> None:
    assert streak.length({d(20), d(21), d(29), d(30)}, today=TODAY) == 2


def test_no_activity_is_no_streak() -> None:
    assert streak.length(set(), today=TODAY) == 0


def test_future_dates_are_ignored_rather_than_trusted() -> None:
    """Clock skew must not be able to inflate a streak."""
    assert streak.length({d(30), d(31)}, today=TODAY) == 1


@pytest.mark.parametrize(
    ("days", "expected"),
    [({d(30)}, False), ({d(29)}, True), (set(), False)],
)
def test_at_risk_means_alive_but_nothing_done_today(days: set[date], expected: bool) -> None:
    assert streak.at_risk(days, today=TODAY) is expected
