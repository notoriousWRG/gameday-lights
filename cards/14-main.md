# Card: CLI and wiring

**Target files:** app/main.py, app/dispatch/dispatcher.py (add `resolve_pattern`, reused by `make_planner`), app/espn/replay.py (add `start_time`), tests/test_main.py
**Goal:** `game-lights` CLI wiring everything together: `run`, `run --replay DIR`, `discover`, `test-effect score --team GB`.

## Context to read (read-only)
- app/config.py, app/watcher.py, app/dispatch/dispatcher.py, app/bulbs/wiz.py, app/espn/client.py, app/espn/replay.py
- DECISIONS.md: Phase 1 run row (`dispatch_enabled`)

## Contract
- `main(argv=None) -> int`; global `--config PATH` (default `config.toml`), `-v`; config errors print the message and return 2
- `run`: live ESPN, real bulbs only when `dispatch_enabled` and not `--dry-run`; otherwise `DryRunBulb`. Calls `dispatcher.recover()` first. SIGTERM/SIGINT stop cleanly
- `run --replay DIR [--speed N] [--fresh]`: always dry-run, virtual clock (default 60x), separate `<db>.replay.db` so it never mixes with live state; prints an events summary with detected -> fired times
- `discover [--broadcast ADDR]`: prints IP and MAC of WiZ bulbs
- `test-effect score --team ABBR [--dry-run]`: plays the team's pattern on its bulbs, snapshot and restore

## Constraints
- No new ESPN call sites outside `EspnClient`.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Replaying a synthetic game end to end through `main()` yields the expected events
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
