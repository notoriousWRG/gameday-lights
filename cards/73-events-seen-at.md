# Card: Record when a score showed on the TV

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/store.py, tests/test_store.py (the only files to edit)
**Goal:** Each event can carry the moment someone said it showed on their TV, so the lag can be measured in the app.

## Contract
- Schema v4: `events.seen_at` (nullable); `Event.seen_at` and `Event.lag_s` (seen minus detected, negative if the TV was ahead)
- `Store.mark_seen(key, when)` (None clears; False for an unknown key) and `Store.seen_events(limit)`
- A v3 database migrates in place and keeps every row (checked on a read-only copy of the real database: 3 events, 100 games and all five settings sections survived)
- Rolling back: a v4 database is refused by older code ("schema 4 is newer than this app"), so keep a copy of the database before first running this version if a rollback might be needed

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
