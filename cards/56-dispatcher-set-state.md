# Card: Dispatcher sets a bulb's state through its queue

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/dispatch/dispatcher.py, tests/test_dispatcher.py (the only files to edit)
**Goal:** A manual light change waits its turn on the per-bulb queue, so it never lands in the middle of an effect and is never undone by that effect's restore.

## Contract
- `Dispatcher.set_state(name, state) -> datetime` runs under the bulb's lock; unknown bulb is `KeyError`
- `Dispatcher.current_state(name) -> BulbState` (read, under the same lock)
- Not recorded as an event; dry-run bulbs just log
- If an effect is playing, the change starts after its restore, so the new state is what stays

## Constraints
- Do not change event handling or `play_now`. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
