# Card: One copy of the color helpers and defaults

**Status:** done 2026-11-08 (awaiting review). Note: `to_hex` and `DEFAULT_COLORS` live in app/effects.py.
**Target files:** app/effects.py, app/settings.py, app/config.py, app/dispatch/dispatcher.py, app/main.py, app/web/status.py, tests/test_effects.py (the only files to edit)
**Goal:** Hex formatting and the fallback colors exist once.

## Contract
- `to_hex(color)` and `DEFAULT_COLORS` live in `app/effects.py`; the copies in settings.py, status.py, dispatcher.py, main.py and config.py are removed and imported instead
- No behavior change; `parse_color` and `to_hex` round-trip is tested

## Constraints
- Pure refactor: the whole suite passes unchanged. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
