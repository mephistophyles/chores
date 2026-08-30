-- Chore config (categories + chores) and the append-only completion log.
--
-- Cycles are derived, never stored as "current": a category has a cycle
-- (daily / weekly / monthly / none) and every completion event is stamped with
-- the period key it belongs to. Opening the app on a new day or in a new week
-- therefore shows an empty board without any job needing to run.

CREATE TABLE chore_categories (
  id            BIGSERIAL PRIMARY KEY,
  household_id  UUID NOT NULL,
  name          TEXT NOT NULL,
  cycle         TEXT NOT NULL CHECK (cycle IN ('daily', 'weekly', 'monthly', 'none')),
  descriptor    TEXT NOT NULL DEFAULT '',
  position      INTEGER NOT NULL DEFAULT 0,
  archived_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    TEXT NOT NULL
);
ALTER TABLE chore_categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY chore_categories_household ON chore_categories
  USING (household_id = current_setting('app.household_id', true)::uuid)
  WITH CHECK (household_id = current_setting('app.household_id', true)::uuid);
CREATE INDEX chore_categories_household_idx
  ON chore_categories (household_id, position, id);

CREATE TABLE chores (
  id            BIGSERIAL PRIMARY KEY,
  household_id  UUID NOT NULL,
  category_id   BIGINT NOT NULL REFERENCES chore_categories (id),
  text          TEXT NOT NULL,
  assignee      TEXT,                -- optional label, free text; NULL = anyone
  position      INTEGER NOT NULL DEFAULT 0,
  archived_at   TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    TEXT NOT NULL
);
ALTER TABLE chores ENABLE ROW LEVEL SECURITY;
CREATE POLICY chores_household ON chores
  USING (household_id = current_setting('app.household_id', true)::uuid)
  WITH CHECK (household_id = current_setting('app.household_id', true)::uuid);
CREATE INDEX chores_household_category_idx
  ON chores (household_id, category_id, position, id);

-- Append-only. Unchecking writes a 'uncheck' row rather than deleting, so the
-- log answers "who did what, when" for every period that has ever existed.
CREATE TABLE chore_events (
  id            BIGSERIAL PRIMARY KEY,
  household_id  UUID NOT NULL,
  chore_id      BIGINT NOT NULL REFERENCES chores (id),
  period_key    TEXT NOT NULL,       -- '2026-08-28' | '2026-W35' | '2026-08' | 'all'
  action        TEXT NOT NULL CHECK (action IN ('check', 'uncheck')),
  user_id       TEXT NOT NULL,
  occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE chore_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY chore_events_household ON chore_events
  USING (household_id = current_setting('app.household_id', true)::uuid)
  WITH CHECK (household_id = current_setting('app.household_id', true)::uuid);
CREATE INDEX chore_events_current_idx
  ON chore_events (household_id, period_key, chore_id, id DESC);
CREATE INDEX chore_events_recent_idx
  ON chore_events (household_id, id DESC);
