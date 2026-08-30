"""The rollover rules are the heart of the app, so they get pinned here.

`chores.cycles` reads WEEK_START and TIMEZONE at import, so the module is
imported once with a fixed environment.
"""

import os
from datetime import date

os.environ.setdefault("DATABASE_URL", "postgresql:///unused")
os.environ.setdefault("HOUSEHOLD_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("WEEK_START", "0")
os.environ.setdefault("TIMEZONE", "UTC")

from chores import cycles  # noqa: E402


def test_daily_key_is_the_date():
    assert cycles.period_key("daily", date(2026, 8, 28)) == "2026-08-28"


def test_weekly_key_is_stable_within_a_week():
    monday = date(2026, 8, 24)
    sunday = date(2026, 8, 30)
    assert cycles.period_key("weekly", monday) == cycles.period_key("weekly", sunday)


def test_weekly_key_changes_at_the_week_boundary():
    sunday = date(2026, 8, 30)
    next_monday = date(2026, 8, 31)
    assert cycles.period_key("weekly", sunday) != cycles.period_key("weekly", next_monday)


def test_monthly_key_ignores_the_day():
    assert cycles.period_key("monthly", date(2026, 8, 1)) == "2026-08"
    assert cycles.period_key("monthly", date(2026, 8, 31)) == "2026-08"


def test_none_cycle_never_rolls_over():
    assert cycles.period_key("none", date(2026, 1, 1)) == "all"
    assert cycles.period_key("none", date(2030, 12, 31)) == "all"
    assert cycles.previous_key("none", date(2026, 8, 28)) is None


def test_previous_keys_step_back_one_period():
    assert cycles.previous_key("daily", date(2026, 8, 28)) == "2026-08-27"
    assert cycles.previous_key("weekly", date(2026, 8, 28)) == "2026-08-17"
    assert cycles.previous_key("monthly", date(2026, 8, 28)) == "2026-07"


def test_previous_month_crosses_the_year_boundary():
    assert cycles.previous_key("monthly", date(2026, 1, 15)) == "2025-12"


def test_labels_are_produced_for_every_cycle():
    day = date(2026, 8, 28)
    for cycle in cycles.CYCLES:
        assert cycles.period_label(cycle, day)
