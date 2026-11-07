# Card: Effect dispatcher

**Target files:** app/dispatch/dispatcher.py, tests/test_dispatcher.py (the only files to edit)
**Goal:** Wait out each event's delay, then play its pattern on the team's bulbs: one effect at a time per bulb, always snapshot and restore, record fired_at and status.

## Context to read (read-only)
- app/store.py: `Event`, `Store.mark_event`, `pending_events`
- app/bulbs/base.py: `BulbAdapter`, `DryRunBulb`, `Pattern`
- app/effects.py, app/config.py: used by `make_planner`
- DECISIONS.md: Overlap, Restart, Delay rows

## Contract
- `Dispatcher(store, bulbs: dict[str, BulbAdapter], planner, now=utc_now, sleep=asyncio.sleep, dry_run=False)`
- `planner(event) -> (Pattern, [bulb names])`; `make_planner(config, team_colors, store)` builds one from config (config colors override ESPN's)
- `schedule(event) -> Task`; `wait_idle()`; `aclose()`; `recover()` marks pending events already past due `skipped_restart` and schedules the rest
- Per-bulb `asyncio.Lock` (FIFO): the next effect starts only after the previous one restored
- `fired_at` = when the effect actually started (after any queueing). Status: `fired`, `dry_run` (when `dry_run`), or `failed` (snapshot/flash error; restore is still attempted)

## Constraints
- Tests use fake bulbs and a fake clock/sleep; nothing touches hardware.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Event due 45 s out sleeps exactly 45 s; two events on one bulb never overlap; a flash error still restores
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
