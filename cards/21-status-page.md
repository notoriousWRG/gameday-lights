# Card: status page

**Target files:** app/web/__init__.py, app/web/status.py, app/web/status.html, app/main.py, tests/test_web_status.py, pyproject.toml (fastapi, uvicorn)
**Goal:** A LAN-only page and JSON endpoint showing what the server is doing, served from the `run` process.
**Contract:**
- `GET /api/status` -> JSON: version, now, uptime, mode (`live`/`dry_run`), teams, bulbs `{name, ip, ping_ms|null}` (ping cached 30 s, 3 s timeout), watcher stats, `watching`, upcoming games `{id, name, start_utc, status}`, last 3 finished games, last 25 events `{key, game, team, label, delta, status, detected_at, due_at, fired_at, fire_delay_s}`
- `GET /` -> one static HTML page that renders the JSON with `textContent` only (ESPN strings are never inserted as HTML) and refreshes every 10 s
- No write endpoints. `[web].enabled=false` starts nothing. A bind failure is logged and does not stop the watcher
**Constraints:** async handlers only (the sqlite connection lives on the event loop thread); never command the bulb except `ping()`.
**Done when:** `uv run pytest` and `uv run ruff check` pass; the page renders in a browser; only the target files changed.

**Also touched:** `app/main.py` gained `run_tasks` (cancel, then wait for every task's cleanup; a second cancel aborts uvicorn's shutdown and prints a traceback). uvicorn is subclassed so it never installs its own SIGINT/SIGTERM handlers.
