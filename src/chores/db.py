"""Connection pool and per-request RLS context."""

import logging
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

log = logging.getLogger("chores.db")

pool = ConnectionPool(
    conninfo=config.DATABASE_URL,
    min_size=1,
    max_size=5,
    timeout=10,
    kwargs={"row_factory": dict_row, "connect_timeout": 10},
    open=False,
)


@contextmanager
def session(user_id: str):
    """A transaction with RLS context set from the resolved identity.

    `user_id` comes from the auth layer, never from a request body or query
    string, and is bound as a parameter so it cannot be injected.
    """
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.household_id', %s, true),"
                    "       set_config('app.user_id', %s, true)",
                    (config.HOUSEHOLD_ID, user_id),
                )
            yield conn


def check() -> None:
    """Raise if the database is unusable. Used by /healthz."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
