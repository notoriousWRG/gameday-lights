# Card: live apply

**Target files:** app/watcher.py, app/dispatch/dispatcher.py, app/web/status.py, app/main.py, tests/test_watcher.py, tests/test_dispatcher.py, tests/test_web_status.py, tests/test_main.py
**Goal:** Settings edits take effect in the running server with no restart.
**Contract:**
- `Watcher`, `make_planner`, `make_bulb_pulse` and `create_app` accept a `Config` or a callable returning the current one (a plain `Config` still works), and read it at use time
- Watcher: `request_sync()` makes the run loop sync schedules now (it wakes from its sleep); `on_config_changed(old, new)` requests a sync when the followed teams change; first sight of a team is tracked explicitly (`league, game, team`) and forgotten when the team is unfollowed, so a team followed mid-game baselines on its first poll and fires from the next score on; only games of followed teams are polled
- `Dispatcher.set_bulbs(bulbs)` swaps the bulb registry, keeping the same lock (and so the serial queue) for a bulb that stays; `Dispatcher.bulbs` exposes the current dict; the page's bulb list, pings and Pulse button follow it
- `main`: `run` and `test-effect` use the stored settings (seeded from `config.toml` on first start, a warning when the file differs), a settings subscriber reconciles bulbs (unchanged bulbs keep their adapter) and refreshes ESPN colors for new teams; CLI `config export [--no-secrets]` and `config import --force`; replay keeps using the TOML
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
