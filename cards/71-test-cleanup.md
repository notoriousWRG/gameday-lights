# Card: Shared test fixtures

**Status:** done 2026-11-08 (awaiting review). Note: shared web test helpers are in `tests/support.py` (plain helpers, not fixtures, so not conftest.py); `test_web_status.py` split into status, play, effects and setup files (427 tests before and after). The fakes in test_dispatcher.py and test_watcher.py were not unified.
**Target files:** tests/conftest.py, tests/test_web_status.py, tests/test_web_settings.py, tests/test_dispatcher.py, tests/test_watcher.py (the only files to edit)
**Goal:** The helpers copied between test files (Recorder bulbs, fake clocks, app builders, `client`) live in conftest, and the 800-line web test file is split by area.

## Contract
- `tests/conftest.py` holds the shared fakes; test files import them
- `test_web_status.py` splits into status, pulse/test, matrix and discovery files; no test is dropped (same count before and after)

## Constraints
- Test count must not go down. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
