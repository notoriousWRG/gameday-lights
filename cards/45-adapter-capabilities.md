# Card: adapter capabilities

**Status:** done 2026-11-08 (G16, awaiting review)
**Target files:** app/bulbs/base.py, app/bulbs/wiz.py, app/bulbs/govee.py, tests/test_bulbs_base.py, tests/test_bulbs_wiz.py, tests/test_bulbs_govee.py
**Goal:** Each adapter declares what its fixture can do, so the effect layer offers only effect kinds the fixture supports and can tell whether restore is reliable.

## Context to read (read-only)
- app/bulbs/base.py: `BulbAdapter`, `Pattern`, `MIN_HOLD_S`
- DECISIONS.md: "One project: per-fixture, per-team effects"

## Contract
- `Capabilities` frozen dataclass: `kinds: frozenset[str]` (effect kinds supported), `min_hold_s: float`, `segments: int` (1 = whole fixture), `restores_scenes: bool`
- `BulbAdapter.capabilities` class attribute; WiZ and Govee each set theirs. Default: `{"pulse"}`, `MIN_HOLD_S`, 1 segment, `restores_scenes=False`
- `min_hold_s` may be raised by an adapter, never lowered below `MIN_HOLD_S`

- Also: `SegmentFrame`, `SegmentPattern` (per-segment flash cap, validated in the constructor), `capabilities_for(kind, segments)`, `BulbAdapter.play(pattern)` (dispatches on pattern type), `GoveeBulb(segments=N)`, `razer_packet`, `razer_message`, and `DryRunBulb(capabilities=)`
- Status: done 2026-11-08

## Constraints
- Do not change command behavior. Do not touch config, settings or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A test shows an adapter cannot lower `min_hold_s` below the cap
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
