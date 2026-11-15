# Card: Calibrate screen

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/web/status.html, app/web/static/screens.js, app/web/static/nav.js, tests/test_web_calibration.py (the only files to edit)
**Goal:** A Calibrate tab to measure the delay during a game without the terminal probe.

## Contract
- Lists the latest scores as they are detected; each has an "I see it on TV" button, then shows its lag and an Undo; refreshes every 3 s while open
- Summary: delay now, readings, median and range, and "Use N seconds", which saves `household.delay_s` through the settings API with If-Match; disabled when the delay already matches, and when the suggestion is over 180 s (the Settings slider limit; almost surely a late press)
- Checked in a browser in dry-run: readings, undo, summary, Use, saved

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
