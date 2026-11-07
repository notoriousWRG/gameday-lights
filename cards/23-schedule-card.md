# Card: consolidated Schedule card

**Target files:** app/store.py, app/espn/detect.py, app/espn/schedule.py, app/watcher.py, app/web/status.py, app/web/status.html, tests/test_store.py, tests/test_espn_schedule.py, tests/test_watcher.py, tests/test_web_status.py
**Goal:** Replace the Upcoming and Finished cards with one Schedule card listing every game for the followed teams in order: final scores (with W/L) for finished games, a live score for the game in progress, day and time for upcoming ones.
**Contract:**
- Schema v2 (`PRAGMA user_version`): `games` gains `home_abbr`, `home_score`, `away_abbr`, `away_score` (nullable). Existing databases migrate on open; data is kept
- `parse_schedule` fills them from ESPN's schedule JSON; the watcher refreshes them from every scoreboard poll for games in their window, so a game's final score appears when it ends, without waiting for the next schedule sync. A stale schedule response never overwrites a newer status or score
- `/api/status` replaces `upcoming_games` and `finished_games` with `schedule`: rows `{id, start_utc, status, us, opp, home, us_score, opp_score, result}`, from the followed team's side (`result` W/L/T only for finished games)
- Page: one wide card, newest-first is NOT used: chronological, the live or next game highlighted and scrolled into view, text via `textContent`
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser; only the target files changed.
