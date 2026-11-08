# Card: wire segments into make_bulb

**Status:** done 2026-11-08 (added during G16; not in the original draft)
**Target files:** app/main.py, tests/test_main.py
**Goal:** A bulb's configured `segments` reaches its adapter, and the dry-run stand-in reports the same capabilities, so a chase plays on the strip and is accepted in dry-run.

## Contract
- `make_bulb` passes `segments` to `GoveeBulb`; dry-run `DryRunBulb` gets `capabilities_for(kind, segments)`
- Changing `segments` makes `reconcile_bulbs` build a fresh adapter (BulbConfig equality already covers it)

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
