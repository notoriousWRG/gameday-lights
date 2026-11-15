# Card: Update the docs

**Status:** drafted 2026-11-08
**Target files:** README.md, ARCHITECTURE.md, intent.md, DECISIONS.md, config.example.toml, CLAUDE.md, docs/game-day.md (the only files to edit)
**Goal:** The docs describe what exists: Govee, segments, effect layers, the matrix, lights control.

## Contract
- README: install, the screens, the config shape; `config.example.toml` shows `kind`, `segments` and a `fixture_effects` sample
- ARCHITECTURE.md and intent.md: the combined direction (per-fixture effects and light control are in scope; scenes, schedules and arbiter are not yet); one DECISIONS.md section kept current
- CLAUDE.md: the flash-cap rule says per segment for chases; bulbs by kind
- `docs/game-day.md`: a checklist for game day, including how to measure lag on the Calibrate screen (the terminal probe is the fallback) and set the delay

## Constraints
- Ask before editing CLAUDE.md (it is the project's standing instructions). Follow CLAUDE.md.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
