# Card: planner plays a pattern per bulb

**Status:** done 2026-11-08 (G16, awaiting review)
**Target files:** app/dispatch/dispatcher.py, tests/test_dispatcher.py (the only files to edit)
**Goal:** An event plays each of its team's bulbs with that bulb's resolved effect, instead of one pattern on all of them; the Pulse and team-test paths use the same resolution.

## Context to read (read-only)
- app/dispatch/dispatcher.py: `make_planner`, `make_bulb_pulse`, `make_team_pulse`, `Dispatcher._run`
- app/effects.py: `resolve_effect`, `build_effect` (C46, C47)

## Contract
- `Planner` returns `list[tuple[str, Pattern]]` (bulb name, pattern) instead of `(Pattern, list[str])`
- Each bulb's pattern is built from `resolve_effect` plus that bulb's adapter capabilities
- A bulb whose effect fails to build is marked failed alone; the others still play
- Per-bulb serial queues, snapshot/restore and fired_at logging are unchanged

## Constraints
- Do not touch the watcher, settings or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Test: one team with a WiZ bulb and a Govee bulb plays two different patterns for one event
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
