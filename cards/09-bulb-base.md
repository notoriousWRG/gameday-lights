# Card: Bulb adapter interface

**Target files:** app/bulbs/base.py, tests/test_bulbs_base.py (the only files to edit)
**Goal:** Brand-neutral bulb interface, the `Pattern` type with the hard 2-changes/sec cap, and a `DryRunBulb`.

## Context to read (read-only)
- CLAUDE.md: bulb and flash-cap rules
- DECISIONS.md: Flash cap, Default effect rows
- scripts/probe_bulb.py: `pulse_steps` (the behavior this generalizes)

## Contract
- `Color = tuple[int, int, int]`; `MAX_CHANGES_PER_S = 2.0`
- `Step(color, hold_s, brightness=255)`; `Pattern(steps)`; `PatternError(ValueError)`
- `Pattern` validates on construction: non-empty, colors 0-255, brightness 1-255, every `hold_s >= 1/MAX_CHANGES_PER_S`
- `BulbAdapter` (ABC): `name`; abstract `set_color(color, brightness=255)`, `snapshot()` (opaque), `restore(snapshot)`; concrete `flash(pattern)` that applies each step with an injectable `sleep`
- `DryRunBulb(name)`: records calls in `.calls`, logs, never touches hardware

## Constraints
- No brand imports. Config cannot exceed the cap: there is no way to build a faster Pattern.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A Pattern with a 0.4 s hold raises PatternError; 0.5 s is accepted
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
