# Card: Watcher and replay client

**Target files:** app/watcher.py, app/espn/replay.py, tests/test_watcher.py (the only files to edit)
**Goal:** The schedule-sync and game-watch loops: poll only inside watch windows, turn score increases into delayed events, and never replay after a restart. `ReplayClient` stands in for `EspnClient` to drive a recorded game offline.

## Context to read (read-only)
- app/espn/client.py (method names to mirror), app/espn/detect.py, app/espn/schedule.py
- app/store.py, app/dispatch/dispatcher.py, app/config.py
- DECISIONS.md: Score firing, Dedupe key, Restart, Delay rows

## Contract
- `Watcher(config, store, client, dispatcher, now, sleep)`; `await sync_schedule()`; `await poll_once() -> seconds_to_sleep`; `await run()`
- `sync_schedule`: regular + postseason (`seasontype=3`) for each followed team; never moves a game's status backwards
- `poll_once`: HTTP only when a stored game is inside its window (starts within `watch_lead_min`, not final); sleep is `poll_live_s` while live, `poll_break_s` at breaks, pre-game or idle
- First sight of a team in this process is a baseline through the store: a higher score than stored becomes a `skipped_restart` event and never fires
- Later increases: `store.apply_score`; each increase inserts a `pending` event (`due_at = detected_at + delay_s`, detail has old/new/delta/label/abbr) and schedules it; decreases only update the store
- `ReplayClient(dir)`: serves the recorded `NNNN_*.json.gz` scoreboards in order (last one repeats) and synthesizes a team schedule from the first frame

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] TD then PAT yields two events; a restart mid-game (new Watcher, same store) yields no duplicates
- [ ] No HTTP call when no game is in its window
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
