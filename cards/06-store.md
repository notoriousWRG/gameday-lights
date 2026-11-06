# Card: SQLite store

**Target files:** app/store.py, tests/test_store.py (the only files to edit)
**Goal:** Persist games, per-team score and increase counters, and events with a unique dedupe key.

## Context to read (read-only)
- DECISIONS.md: Dedupe key, Restart, Decreases rows
- ARCHITECTURE.md: store line and event shape

## Contract
- `Store(path)` (`":memory:"` allowed); schema created/upgraded via `PRAGMA user_version`
- `upsert_game(Game)`, `get_game(game_id)`, `upcoming_games(now, horizon)`
- `apply_score(game_id, team_id, score) -> ScoreUpdate(prev_score, score, increase_n, increased)`: first sight is a baseline (increased False, increase_n 0); a higher score bumps `increase_n` by exactly 1; a lower score is stored and never touches the counter
- `dedupe_key(game_id, team_id, n)`; `insert_event(Event) -> bool` (False if the key exists); `pending_events()`; `mark_event(dedupe_key, status, fired_at=None)`
- All datetimes are timezone-aware UTC, stored as ISO strings; naive datetimes raise ValueError

## Constraints
- stdlib `sqlite3` only; operations are tiny so they are called directly from asyncio code.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Reversal then re-score yields increase_n 1, 1 (decrease), 2 and distinct dedupe keys
- [ ] Reopening the same file keeps data
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
