# Card: Practice mode API

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/config.py, app/web/routes_calibration.py, app/web/data.py, tests/test_config.py, tests/test_web_calibration.py (the only files to edit)
**Goal:** The page can start and stop practice mode and read the plays with their lag.

## Context to read (read-only)
- app/web/routes_calibration.py: `POST/DELETE /api/events/{key}/seen` already work on any event key, so plays reuse them
- app/web/data.py `calibration()`: builds `by_label` from seen events; the 75th-percentile rule and the 180 s cap stay
- Card 80: `start_practice`, `stop_practice`, `practice_until`

## Contract
- `GET /api/practice` -> `{"active": bool, "until": iso | null, "minutes": int}`
- `PUT /api/practice` body `{"active": true}` starts for `web.practice_minutes`; `{"active": false}` stops. `X-Gameday` required. 409 with a clear message when no followed game is in its watch window ("no game to practice on yet")
- `GET /api/calibration` gains `plays`: recent play events (`key`, `text`, `period`, `clock`, `detected_at`, `seen_at`, `lag_s`) and `play_summary` (count, median, range, suggestion), kept apart from `by_label` so a play can never get its own score delay; `/api/practice` also returns `available`; the list shows only the last 12 hours. `suggested_delay_s` for the overall figure counts scores only: a play reading never changes what a score suggests
- `[web] practice_minutes` (1 to 120, default 20) in config, export/import and `config.example.toml` comment line if that file is not a target here, state it in the report instead

## Constraints
- Every write needs `X-Gameday`; nothing new binds outside the LAN
- A restart leaves practice off; the API says so rather than remembering it

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Start with no game in window -> 409; with one -> 200 and `until` about `practice_minutes` ahead; stop -> inactive
- [ ] Marking a play seen sets its `lag_s`; `by_label["Play"]` appears with the right median; score groups are unchanged
- [ ] `practice_minutes` of 0 or 121 is a config error
- [ ] Only the target files changed
