# Card: Advanced screen (timings)

**Target files:** app/web/status.html, tests/test_web_status.py
**Goal:** An `Advanced` screen (`#/advanced`) to edit the `advanced` section: poll and sync timings, pulse cooldown and final-game hold.
**Contract:**
- Fields with units and one-line help each: `poll_live_s` and `poll_break_s` (min 10 s; say it is a hard floor to be kind to ESPN), `schedule_sync_hours` (min 0.1), `watch_lead_min`, `pulse_cooldown_s` (min 1), `final_hold_min`; "Reset to defaults" fills the draft with 15, 60, 6, 10, 10, 30 (still a draft until Save)
- Client-side `min` attributes are hints only; server 422 messages show under the field
- A short note that `dispatch_enabled` and the web address live in `config.toml` (read from `machine` in `GET /api/settings`, shown read-only, never editable)
- Reached from a quiet link ("Advanced") at the foot of the Settings screen as well as the nav; built on `sectionEditor`; no server changes
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser (a poll below 10 gives a field error, a valid change applies live without restart); only the target files changed.
