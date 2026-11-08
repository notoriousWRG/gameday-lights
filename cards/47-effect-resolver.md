# Card: effect resolver

**Status:** done 2026-11-08 (G16, awaiting review)
**Target files:** app/effects.py, tests/test_effects.py (the only files to edit; shares C46's files, so run after it)
**Goal:** One pure function decides which effect spec and colors a given team plays on a given fixture, layering global -> fixture -> team -> team x fixture.

## Contract
- `resolve_effect(config, team, bulb, espn_colors) -> tuple[EffectSpec, Color, Color]`
- Each layer may set `kind`, any param, `color`, `alt_color`; a later layer overrides an earlier one field by field; unset fields fall through
- ESPN colors are the last fallback for colors only, as today
- No team x fixture layer is required to exist: a config with only the global layer resolves exactly as today

## Constraints
- Pure: no I/O, no clock. Same inputs, same output.
- Do not change dispatcher, settings or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Tests cover each layer overriding the one before, a field falling through, and the global-only case matching today's output
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
