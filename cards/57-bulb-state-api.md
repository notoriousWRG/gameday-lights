# Card: Bulb state API

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/web/status.py, tests/test_web_status.py (the only files to edit)
**Goal:** `GET` and `PUT /api/bulbs/{name}/state` read and set a bulb's current light settings from the web app.

## Contract
- GET returns `{on, color, color_temp_k, brightness}` (color as #rrggbb); 404 for an unknown bulb; 502 if the bulb does not answer
- PUT body takes the same fields (any subset); needs `X-Gameday: 1`; 400 for a bad body or both color and color_temp_k; 422 for out-of-range values
- A bulb can be changed at most every 0.5 s (the same 2/sec ceiling as effects): 429 with the wait; 409 while a pulse or test is playing on it
- Dry-run says nothing was sent, as the pulse endpoint does

## Constraints
- Reuse `ready()`-style guards from the pulse endpoint. Do not touch settings routes. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
