# Card: Set a bulb's current state (adapters)

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/bulbs/base.py, app/bulbs/wiz.py, app/bulbs/govee.py, tests/test_bulbs_base.py, tests/test_bulbs_wiz.py, tests/test_bulbs_govee.py (the only files to edit)
**Goal:** Every adapter can set a bulb to a steady state (on/off, color or white temperature, brightness) and report its current one. This is a plain light setting, not an effect: no snapshot, no restore, no flash cap involved.

## Contract
- `BulbState` frozen dataclass: `on: bool | None`, `color: Color | None`, `color_temp_k: int | None`, `brightness: int | None` (1..255); `None` = leave that part alone; `color` and `color_temp_k` are mutually exclusive
- `BulbAdapter.set_state(state)` and `BulbAdapter.current_state() -> BulbState` (from the same status read as `snapshot`)
- WiZ: PilotBuilder rgb / colortemp / brightness, `turn_off` for `on=False`. Govee: `turn`, `brightness`, `colorwc` with `colorTemInKelvin` for white. DryRunBulb records the call
- Govee scenes and music modes still read back as a plain color (devStatus cannot report them); say so in the docstring

## Constraints
- Do not change effect playback, snapshot or restore. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
