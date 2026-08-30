# Chores

A household chore board. Chores are grouped into categories, each of which runs on a
cycle — daily, weekly, monthly, or none. Ticking a chore records who did it and when.

Three things make it more than a checklist:

- **The board rolls over by itself.** Opening it on a new day, in a new week, or in a
  new month shows a fresh board, with the previous period's tally kept for reference.
- **Every tick is logged against a person**, append-only, so "who actually did the
  bins last week" is answerable.
- **The chore list is editable in the app**, under the *Chore list* tab. Categories,
  cycles, chore wording, ordering, and an optional assignee are all config, not code.

## How rollover works

Nothing runs on a schedule. A category stores its *cycle*, and every event is stamped
with the *period key* of the moment it happened:

| Cycle     | Period key example | Rolls over |
|-----------|--------------------|------------|
| `daily`   | `2026-08-28`       | at midnight |
| `weekly`  | `2026-08-24` (the week's first day) | at the start of the week |
| `monthly` | `2026-08`          | on the 1st |
| `none`    | `all`              | never — a standing list |

The board for a given day asks for the events matching today's key, so a period that has
rolled over simply has no events yet. Nothing is reset, nothing is deleted, and history
for every past period stays queryable. `WEEK_START` decides which weekday a week begins
on and `TIMEZONE` decides when a day ends.

## Assignment

`assignee` is a free-text label on a chore and is entirely optional — an unassigned chore
belongs to whoever gets to it. It is a *label*, not a permission: anybody who can write
can tick anybody's chore. The board has a filter to show one person's chores at a time.

## Configuration

All configuration comes from the environment, populated by `deploy.sh` from SSM.

| Parameter | Required | Default | Purpose |
|---|---|---|---|
| `/home/<slug>/DATABASE_URL` | yes | — | this app's own Postgres database |
| `/home/shared/HOUSEHOLD_ID` | yes | — | platform-wide; never create a per-app copy |
| `/home/chores/AUTH_MODE` | no | `none` | `none` for single-user, `proxy` to read the identity headers |
| `/home/chores/SINGLE_USER_ID` | no | `me` | the name recorded in the log while `AUTH_MODE=none` |
| `/home/chores/WRITE_ROLES` | no | `owner,member` | roles allowed to tick and to edit the chore list |
| `/home/chores/TIMEZONE` | no | `UTC` | IANA zone deciding when a day rolls over |
| `/home/chores/WEEK_START` | no | `0` | weekday a week starts on, 0=Monday … 6=Sunday |

`WEB_DIST_PATH` and `MIGRATIONS_PATH` are set in the Dockerfile and only need overriding
when running outside the image.

Keep `AUTH_MODE=none` until forward-auth is live. Under `none` every completion is logged
against `SINGLE_USER_ID`; flipping to `proxy` once a second person is on the tailnet makes
attribution real without any data migration, because the log already has a `user_id`
column on every row.

## Roles

| Role | May |
|---|---|
| `owner`, `member` | read the board, tick chores, edit the chore list |
| `viewer` | read the board and the log only |

Unknown user or unknown role is a 403.

## API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/healthz` | 200 only when the database answers and the assets are mounted |
| `GET` | `/api/board` | today's board; `?on=YYYY-MM-DD` to view another day |
| `POST` | `/api/chores/{id}/check` | `{"checked": true\|false}`; returns the updated board |
| `GET` | `/api/history` | newest-first log, keyset paginated via `limit` and `before_id` |
| `GET` | `/api/config` | the editable chore list |
| `POST`/`PATCH`/`DELETE` | `/api/config/categories[/{id}]` | delete is a soft archive |
| `POST`/`PATCH`/`DELETE` | `/api/config/chores[/{id}]` | delete is a soft archive |

Deleting is always a soft archive: the completion log keeps pointing at the row, so
removing a chore never destroys the record of it having been done.

## Dependencies

Three, each carrying its weight:

- **fastapi** — routing plus request validation, so bad input is rejected at the edge
  rather than in a handler.
- **uvicorn** — the ASGI server; `[standard]` supplies the signal handling that lets
  in-flight requests drain on SIGTERM.
- **psycopg[binary,pool]** — Postgres driver and connection pool. The pool matters
  because RLS context is set per transaction.

No frontend build: the UI is one static HTML file the app serves.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e . pytest
docker run -d --name chores-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=chores \
  -p 55432:5432 postgres:16-alpine

export DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/chores
export HOUSEHOLD_ID=11111111-2222-3333-4444-555555555555
export WEB_DIST_PATH=$PWD/web MIGRATIONS_PATH=$PWD/migrations

.venv/bin/python -m chores.migrate          # migrates, then seeds a default list
.venv/bin/pytest -q
.venv/bin/uvicorn chores.app:app --port 8099
```

Migrations are numbered and forward-only in CI; each has a matching `.down.sql` applied
by hand for a rollback.

## Deployment

Follows the platform deploy contract: GitHub Actions builds `linux/arm64`, pushes to
GHCR, and calls `/opt/home/bin/deploy.sh chores <sha>`, which handles secrets,
migrations, health gating, rollback, and launchpad registration. The container listens on
8000 and is published on `127.0.0.1:8014`.

## Licence

MIT — see `LICENSE`.
