"""Runtime configuration. Environment only — never a config file, never a literal."""

import os
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set; it must come from SSM via .env.runtime")
    return value


DATABASE_URL = _required("DATABASE_URL")
HOUSEHOLD_ID = _required("HOUSEHOLD_ID")

# 'none' runs single-user; 'proxy' reads the identity headers nginx sets.
AUTH_MODE = os.environ.get("AUTH_MODE", "none").strip().lower()

# The identity recorded in the completion log while AUTH_MODE=none.
SINGLE_USER_ID = os.environ.get("SINGLE_USER_ID", "me").strip()

# Roles permitted to write. Viewers may read the board but not tick anything.
WRITE_ROLES = frozenset(
    r.strip() for r in os.environ.get("WRITE_ROLES", "owner,member").split(",") if r.strip()
)
KNOWN_ROLES = WRITE_ROLES | {"viewer"}

WEB_DIST = Path(os.environ.get("WEB_DIST_PATH", "/app/web"))
MIGRATIONS_DIR = Path(os.environ.get("MIGRATIONS_PATH", "/app/migrations"))

# Weekday the weekly cycle rolls over on: 0=Monday … 6=Sunday.
WEEK_START = int(os.environ.get("WEEK_START", "0"))

# Local timezone used to decide which day/week/month it currently is.
TIMEZONE = os.environ.get("TIMEZONE", "UTC")

MAX_PAGE_SIZE = 200
