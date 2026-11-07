# Card: bulb discovery endpoint

**Target files:** app/web/status.py, app/main.py, tests/test_web_settings.py
**Goal:** `POST /api/bulbs/discover` lists WiZ bulbs found on the LAN, marking the ones already stored.
**Contract:**
- Returns `[{ip, mac, known, name}]`; `known` is true when the MAC (or, without one, the IP) matches a stored bulb, and `name` is that bulb's name
- 403 without `X-Gameday: 1`; 409 while a discovery is already running; 502 with the error text if discovery fails; a broadcast takes about 5 s, so the handler awaits it without blocking other requests
- `create_app` gets an optional `discover_bulbs` callable (default none, route absent without it); `main.py` passes `discover_wiz`
- Never returns signing keys; no settings are changed by discovery
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
