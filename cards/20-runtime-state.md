# Card: runtime state for the status page

**Target files:** app/watcher.py, app/bulbs/base.py, app/bulbs/wiz.py, tests/test_watcher.py, tests/test_bulbs_base.py, tests/test_bulbs_wiz.py
**Goal:** Expose what the page needs without changing behavior.
**Contract:**
- `WatcherStats` on `Watcher.stats`: `started_at`, `last_sync_at`, `last_poll_at`, `last_ok_at`, `polls`, `errors`, `last_error`, `watching` (game names in their window)
- `BulbAdapter.ping() -> float | None`: round-trip seconds, or None if unreachable. WiZ: one direct `getPilot`, no re-discovery, never changes bulb state. `DryRunBulb.ping()` returns 0.0
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
