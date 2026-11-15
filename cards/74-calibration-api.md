# Card: Calibration endpoints

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/web/data.py, app/web/routes_calibration.py, app/web/status.py, tests/test_web_calibration.py (the only files to edit)
**Goal:** The web app can stamp an event as seen on the TV and report what the readings say the delay should be.

## Contract
- `POST /api/events/{key}/seen` stamps the server's clock (404 unknown; needs X-Gameday); `DELETE` clears it
- `GET /api/calibration`: `{delay_s, events (newest 12), n, median_s, min_s, max_s, suggested_delay_s}`; the suggestion is the 75th percentile of the lags (nearest rank), rounded up and never below 0, so a flash is never early
- `/api/status` events also carry `seen_at` and `lag_s`

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
