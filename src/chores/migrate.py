"""Forward migrations, run by deploy.sh before the new container starts.

Each numbered .sql file runs once inside its own transaction and is recorded in
schema_migrations. A matching .down.sql sits beside every file for rollback,
which is applied by hand rather than automatically.
"""

import logging
import sys

import psycopg
from psycopg.rows import dict_row

from . import config
from .seed import seed_if_empty

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("chores.migrate")

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def pending(conn) -> list:
    files = sorted(
        p for p in config.MIGRATIONS_DIR.glob("*.sql") if not p.name.endswith(".down.sql")
    )
    if not files:
        raise RuntimeError(f"no migrations found in {config.MIGRATIONS_DIR}")
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in cur.fetchall()}
    return [p for p in files if p.stem not in applied]


def main() -> int:
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(BOOTSTRAP)
        conn.commit()

        for path in pending(conn):
            log.info('{"event": "migrate.apply", "version": "%s"}', path.stem)
            with conn.cursor() as cur:
                cur.execute(path.read_text())
                cur.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,)
                )
            conn.commit()

        seeded = seed_if_empty(conn, config.HOUSEHOLD_ID)
        conn.commit()
        log.info('{"event": "migrate.done", "seeded": %s}', "true" if seeded else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
