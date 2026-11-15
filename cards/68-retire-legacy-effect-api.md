# Card: Remove the old single-pulse API

**Status:** done 2026-11-08 (awaiting review). Note: `resolve_pattern` and `make_team_pulse` are gone; the `test-effect` CLI plays each bulb's real effect; the segments probe imports the razer helpers from app/bulbs/govee.py.
**Target files:** app/effects.py, app/config.py, app/dispatch/dispatcher.py, app/main.py, app/web/status.py, scripts/probe_govee_segments.py, tests/test_effects.py, tests/test_dispatcher.py, tests/test_main.py, tests/test_web_status.py (the only files to edit)
**Goal:** Code that only existed for the pre-layers world goes away.

## Contract
- After card 65: remove `make_team_pulse` and `resolve_pattern`; `test-effect` in the CLI uses `make_cell_pattern` per bulb
- `build_pattern` stays only as the pulse builder inside `build_effect`; `EffectConfig` stays as the global layer
- `scripts/probe_govee_segments.py` imports the razer helpers from `app/bulbs/govee.py` instead of its own copy

## Constraints
- No behavior change for users. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
