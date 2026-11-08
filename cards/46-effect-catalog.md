# Card: effect catalog

**Status:** done 2026-11-08 (G16, awaiting review)
**Target files:** app/effects.py, tests/test_effects.py (the only files to edit)
**Goal:** `build_pattern` becomes `build_effect`: an `EffectSpec(kind, params)` plus colors and a fixture's `Capabilities` produce a `Pattern`, for pulse now and further kinds later.

## Context to read (read-only)
- app/effects.py: `EffectConfig`, `build_pattern`, `parse_color`
- app/bulbs/base.py: `Pattern`, `Step`, `Capabilities` (from C45)

## Contract
- `EffectSpec(kind: str, params: dict)`; `KINDS` registry mapping kind name to a builder and its allowed params
- `pulse` params are today's `pulses`, `duration_s`, `brightness`, with the same results as `build_pattern`
- `chase` is the first non-pulse kind: chunks of the team color and alt color rotating along a fixture's segments, params `chunk`, `speed` (segments/s), `duration_s`. Produces a `SegmentPattern` (frames of per-segment colors); a fixture with 1 segment does not offer it. Added only after the flash-cap decision is written down (per segment, a change happens once per `chunk` segments of travel, so `speed / chunk` must stay under the cap)
- Breathe and sparkle stay later
- A kind the fixture's capabilities do not list raises `ValueError` naming the kind and the fixture
- `EffectConfig` and `build_pattern` stay as thin wrappers until the resolver (C47) replaces their callers

## Constraints
- Pattern validation still enforces the flash cap. Do not touch dispatcher, config or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Existing pulse tests pass unchanged
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
