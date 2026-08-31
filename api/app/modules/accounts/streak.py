"""Day-streak arithmetic. Pure: no database, no clock.

A streak is the run of consecutive days on which a user did something that
counts. Isolating the arithmetic from I/O is what makes the boundaries -
today, yesterday, a gap - testable exactly.
"""

from datetime import date, timedelta


def length(active_days: set[date], today: date) -> int:
    """How many consecutive days the run covers.

    Counting starts today if there is activity today, otherwise yesterday: the
    day is not over, and breaking a streak at midnight would be punitive.
    Days in the future are ignored so clock skew cannot inflate a streak.
    """
    days = {day for day in active_days if day <= today}
    if not days:
        return 0

    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0

    run = 0
    while cursor in days:
        run += 1
        cursor -= timedelta(days=1)
    return run


def at_risk(active_days: set[date], today: date) -> bool:
    """A live streak with nothing done today. The nudge worth showing."""
    return length(active_days, today) > 0 and today not in active_days
