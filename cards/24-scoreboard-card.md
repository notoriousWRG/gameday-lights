# Card: Scoreboard card

**Target files:** app/espn/schedule.py, app/watcher.py, app/config.py, config.example.toml, app/web/status.py, app/web/status.html, tests/test_espn_schedule.py, tests/test_watcher.py, tests/test_config.py, tests/test_web_status.py
**Goal:** A card at the top of the status page. During an active game window it shows one scoreboard per watched game (teams, records, score, per-period scores, clock/period or status, possession and down/distance when ESPN provides them, broadcast, venue) and says that it is polling and how often. Otherwise it highlights the next upcoming game across all followed teams, with a live countdown.
**Contract:**
- `parse_scoreboard_game(event)` (pure): the fields above from one scoreboard event; missing fields become None, never errors; `situation` is read defensively (no live sample exists yet)
- Watcher keeps `stats.live[game_id]` (latest parsed game + `updated_at`, `ended_at`), `stats.watching_ids`, and `stats.poll_interval_s` (None when not polling)
- `[web].final_hold_min` (default 30, min 0): a finished game stays on the card this long, then the card falls back to the next game
- `/api/status.scoreboard`: `{mode: live|pre|final|next|idle, polling: {active, interval_s, last_poll_at, lead_min}, games: [...], next: {...}|null, next_in_week: bool}`; "this week" means kickoff within 7 days
- Page: text via `textContent` only; countdown ticks every second client-side; the polling dot respects reduced motion
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser in each mode; only the target files changed.
