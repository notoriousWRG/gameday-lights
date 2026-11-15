# Card: Calibrate each kind of score

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/web/data.py, app/web/static/screens.js, tests/test_web_calibration.py (the only files to edit)
**Goal:** The Calibrate screen measures and applies a delay per kind of score, and Settings shows the per-kind fields.

## Contract
- `GET /api/calibration` adds `by_label`: per kind, n, median, range, suggested delay (75th percentile, rounded up), the delay it uses now; touchdowns first on a tie
- Calibrate: one row per kind with its own "Use N s" (over 180 s is refused as a probable late press) and "Use all of these"; the kind with the most readings sets the default delay and the others get their own
- Settings: "A different delay for one kind of score" with Touchdown, Extra point, Field goal and Goal (hockey); blank means the default

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
