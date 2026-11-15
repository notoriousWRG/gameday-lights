# Card: A different delay per kind of score

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/config.py, app/watcher.py, app/settings.py, app/settings_service.py, tests/test_config.py, tests/test_watcher.py, tests/test_settings.py, tests/test_settings_service.py (the only files to edit)
**Goal:** An extra point can have a shorter delay than a touchdown.

## Contract
- Observed 2026-11-08: calibrated on touchdowns, the extra point's flash came a second or two before it showed on TV (ESPN reports it at a different moment relative to the picture)
- `[general.delay_by_label]` (TOML) and `household.delay_by_label` (settings): label -> seconds, 0 to 180; labels are those on events (TD, PAT, FG, TD+PAT, TD+2pt, safety/2pt, score); anything without one uses `delay_s`
- The watcher picks the delay by the event's label when it records the event; unset behaves exactly as before; export and import carry it

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
