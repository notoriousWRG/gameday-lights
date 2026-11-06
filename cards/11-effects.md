# Card: Effects

**Target files:** app/effects.py, tests/test_effects.py (the only files to edit)
**Goal:** Turn an effect config plus team colors into a `Pattern`. One effect type for Phase 1: `score`, a slow pulse.

## Context to read (read-only)
- app/bulbs/base.py: `Pattern`, `Step`, the cap
- DECISIONS.md: Default effect row (5 pulses, ~6 s, team color <-> alternate)

## Contract
- `parse_color(s)` accepts `"#RRGGBB"`, `"RRGGBB"` or `"R,G,B"`; raises ValueError otherwise
- `EffectConfig(pulses=5, duration_s=6.0, color=None, alt_color=None, brightness=255)`
- `build_pattern(effect, team_primary, team_alternate) -> Pattern`; config colors override team colors; pulse count and duration must satisfy the cap or `PatternError` propagates

## Constraints
- Do not touch base.py.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Default effect gives 10 steps of 0.6 s alternating primary/alternate
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
