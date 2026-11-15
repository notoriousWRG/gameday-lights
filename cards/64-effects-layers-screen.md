# Card: Effects screen: bulb and team defaults, simpler matrix

**Status:** done 2026-11-08 (awaiting review). Note: `app/web/status.py` also changed: `/api/effects/matrix` now lists every bulb with its kinds.
**Target files:** app/web/status.html, tests/test_web_status.py (the only files to edit)
**Goal:** The fixture and team layers get a screen, and the matrix stops showing every field for every cell.

## Contract
- A "Bulb defaults" row per bulb (the `effects.fixtures` layer) and a "Team effect" row per team (the team `effects` layer): kind, parameters, colors
- Matrix cells show the summary and a "Customize" button; fields appear only when opened or when the cell already has an override
- Plain wording: "Same as above" says what it follows, e.g. "Same as Packers' default"
- Needs card 61 first (shared save flow)

## Constraints
- Reuse the existing section editors and `GET /api/effects/matrix`. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
