"""Period keys.

The board never stores "the current week". It stores a cycle per category and
stamps every event with the key of the period it happened in, so the correct
cycle is simply whichever key today resolves to — opening the app after a
rollover shows a fresh board with no job having run.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config

CYCLES = ("daily", "weekly", "monthly", "none")


def today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def week_start(day: date) -> date:
    """First day of the week containing `day`, honouring WEEK_START."""
    offset = (day.weekday() - config.WEEK_START) % 7
    return day - timedelta(days=offset)


def period_key(cycle: str, day: date) -> str:
    if cycle == "daily":
        return day.isoformat()
    if cycle == "weekly":
        return week_start(day).isoformat()
    if cycle == "monthly":
        return f"{day.year:04d}-{day.month:02d}"
    if cycle == "none":
        return "all"
    raise ValueError(f"unknown cycle {cycle!r}")


def previous_key(cycle: str, day: date) -> str | None:
    """The key of the period before the one containing `day`."""
    if cycle == "daily":
        return period_key(cycle, day - timedelta(days=1))
    if cycle == "weekly":
        return period_key(cycle, week_start(day) - timedelta(days=1))
    if cycle == "monthly":
        first = day.replace(day=1)
        return period_key(cycle, first - timedelta(days=1))
    return None


def period_label(cycle: str, day: date) -> str:
    """Human label for the period a category is currently in."""
    if cycle == "daily":
        return day.strftime("%a %-d %b")
    if cycle == "weekly":
        start = week_start(day)
        end = start + timedelta(days=6)
        if start.month == end.month:
            return f"{start.strftime('%-d')}–{end.strftime('%-d %b')}"
        return f"{start.strftime('%-d %b')}–{end.strftime('%-d %b')}"
    if cycle == "monthly":
        return day.strftime("%B %Y")
    return "Ongoing"
