# Card: Pulse button on the status page

**Target files:** app/web/status.py, app/web/status.html, app/dispatch/dispatcher.py, app/config.py, app/main.py, config.example.toml, tests/test_web_status.py, tests/test_dispatcher.py, tests/test_config.py
**Goal:** A "Pulse" button next to each bulb that runs the same check as `test-effect`: the team's score pattern on that bulb, snapshot and restore. This is the page's first write action, so it is guarded.
**Contract:**
- `POST /api/bulbs/{name}/pulse` -> `{ok, dry_run, duration_s, started_at}`; 403 without the `X-Gameday: 1` header (a cross-site form post cannot set it without a CORS preflight, which we never grant); 404 unknown bulb; 409 already pulsing; 429 inside `[web].pulse_cooldown_s` (default 10, min 1; counted from the end of the last pulse); 502 with the bulb error text
- Goes through `Dispatcher.play_now`, so it queues behind a real effect on the same bulb and never overlaps one; the pattern is the first team that uses the bulb (config colors over ESPN), else the default effect; the 2 changes/sec cap still applies
- Pulses are not events: nothing is written to the events table
- Page: button disabled while pulsing, result text beside it, state survives the 10 s refresh; all text via `textContent`
**Done when:** `uv run pytest` and `uv run ruff check` pass; works in a browser; only the target files changed.
