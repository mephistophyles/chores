"""Data access. Every query is household-scoped and every list is bounded."""

from datetime import date

from . import config
from .cycles import period_key, period_label, previous_key

CATEGORY_LIMIT = 60
CHORE_LIMIT = 1000


def list_categories(conn, include_archived: bool = False) -> list[dict]:
    clause = "" if include_archived else " AND archived_at IS NULL"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, cycle, descriptor, position, archived_at"
            " FROM chore_categories"
            f" WHERE household_id = %s{clause}"
            " ORDER BY position, id LIMIT %s",
            (config.HOUSEHOLD_ID, CATEGORY_LIMIT),
        )
        return cur.fetchall()


def list_chores(conn, include_archived: bool = False) -> list[dict]:
    clause = "" if include_archived else " AND archived_at IS NULL"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, category_id, text, assignee, position, archived_at"
            " FROM chores"
            f" WHERE household_id = %s{clause}"
            " ORDER BY category_id, position, id LIMIT %s",
            (config.HOUSEHOLD_ID, CHORE_LIMIT),
        )
        return cur.fetchall()


def current_state(conn, keys: list[str]) -> dict[int, dict]:
    """Latest event per chore across the given period keys.

    DISTINCT ON collapses the append-only log to one row per chore, so an
    unchecked-then-rechecked item reports the person who last checked it.
    """
    if not keys:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (chore_id) chore_id, period_key, action, user_id, occurred_at"
            " FROM chore_events"
            " WHERE household_id = %s AND period_key = ANY(%s)"
            " ORDER BY chore_id, id DESC",
            (config.HOUSEHOLD_ID, keys),
        )
        rows = cur.fetchall()
    return {r["chore_id"]: r for r in rows if r["action"] == "check"}


def period_counts(conn, keys: list[str]) -> dict[str, int]:
    """How many distinct chores are currently checked in each given period."""
    if not keys:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT period_key, count(*) AS n FROM ("
            "  SELECT DISTINCT ON (chore_id, period_key) chore_id, period_key, action"
            "  FROM chore_events"
            "  WHERE household_id = %s AND period_key = ANY(%s)"
            "  ORDER BY chore_id, period_key, id DESC"
            ") latest WHERE action = 'check' GROUP BY period_key",
            (config.HOUSEHOLD_ID, keys),
        )
        return {r["period_key"]: r["n"] for r in cur.fetchall()}


def board(conn, day: date) -> dict:
    """The whole board for `day`, with each category resolved to its own period."""
    categories = list_categories(conn)
    chores = list_chores(conn)

    keys = {period_key(c["cycle"], day) for c in categories}
    prev_keys = {k for k in (previous_key(c["cycle"], day) for c in categories) if k}
    checked = current_state(conn, sorted(keys))
    prev_counts = period_counts(conn, sorted(prev_keys))

    by_category: dict[int, list] = {}
    for chore in chores:
        entry = checked.get(chore["id"])
        by_category.setdefault(chore["category_id"], []).append(
            {
                "id": chore["id"],
                "text": chore["text"],
                "assignee": chore["assignee"],
                "position": chore["position"],
                "checked": entry is not None,
                "checked_by": entry["user_id"] if entry else None,
                "checked_at": entry["occurred_at"].isoformat() if entry else None,
            }
        )

    out = []
    for cat in categories:
        key = period_key(cat["cycle"], day)
        prev = previous_key(cat["cycle"], day)
        items = by_category.get(cat["id"], [])
        out.append(
            {
                "id": cat["id"],
                "name": cat["name"],
                "cycle": cat["cycle"],
                "descriptor": cat["descriptor"],
                "position": cat["position"],
                "period_key": key,
                "period_label": period_label(cat["cycle"], day),
                "previous_period_key": prev,
                "previous_done": prev_counts.get(prev, 0) if prev else 0,
                "done": sum(1 for i in items if i["checked"]),
                "total": len(items),
                "chores": items,
            }
        )
    return {"date": day.isoformat(), "categories": out}


def record_event(conn, chore_id: int, action: str, user_id: str, day: date) -> dict:
    """Append a check/uncheck for whichever period the chore's category is in."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, cat.cycle FROM chores c"
            " JOIN chore_categories cat ON cat.id = c.category_id"
            " WHERE c.household_id = %s AND c.id = %s AND c.archived_at IS NULL",
            (config.HOUSEHOLD_ID, chore_id),
        )
        row = cur.fetchone()
        if row is None:
            return {}
        key = period_key(row["cycle"], day)
        cur.execute(
            "INSERT INTO chore_events"
            " (household_id, chore_id, period_key, action, user_id)"
            " VALUES (%s, %s, %s, %s, %s)"
            " RETURNING id, chore_id, period_key, action, user_id, occurred_at",
            (config.HOUSEHOLD_ID, chore_id, key, action, user_id),
        )
        return cur.fetchone()


def history(conn, limit: int, before_id: int | None) -> list[dict]:
    """Newest-first page of the completion log. Keyset paginated."""
    clause = " AND e.id < %s" if before_id else ""
    params: list = [config.HOUSEHOLD_ID]
    if before_id:
        params.append(before_id)
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT e.id, e.chore_id, e.period_key, e.action, e.user_id, e.occurred_at,"
            "       c.text AS chore_text, cat.name AS category_name, cat.cycle"
            " FROM chore_events e"
            " JOIN chores c ON c.id = e.chore_id"
            " JOIN chore_categories cat ON cat.id = c.category_id"
            f" WHERE e.household_id = %s{clause}"
            " ORDER BY e.id DESC LIMIT %s",
            params,
        )
        return cur.fetchall()


def assignees(conn) -> list[str]:
    """Distinct assignee labels in use, for the picker."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT assignee FROM chores"
            " WHERE household_id = %s AND assignee IS NOT NULL AND archived_at IS NULL"
            " ORDER BY assignee LIMIT 50",
            (config.HOUSEHOLD_ID,),
        )
        return [r["assignee"] for r in cur.fetchall()]
