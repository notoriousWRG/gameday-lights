# Card: Effects screen matrix

**Status:** done 2026-11-08 (G17, awaiting review). Supporting changes outside the target files: `app/effects.py` `effect_layers` (one definition of the layer order, shared by the resolver and the matrix), `app/dispatch/dispatcher.py` `make_cell_pattern`, `app/main.py` wiring
**Target files:** app/web/status.html, app/web/status.py, tests/test_web_status.py
**Goal:** The Effects screen shows teams x fixtures, lets a layer be set or cleared per cell, and has a Test button per cell that plays exactly what that team would play on that fixture.

## Contract
- A card per followed team with one cell per bulb it uses (`GET /api/effects/matrix`); a cell shows the resolved effect and which layer it came from
- Editing a cell writes the team x fixture layer; clearing it falls back to the layer above
- Kind choices in a cell come from the fixture's capabilities
- Test uses the planner's resolution (C49), not a separate path: `POST /api/effects/test {league, id, bulb}` plays the saved effect through the same guards as the Pulse button

## Constraints
- Reuse `sectionEditor`, `If-Match` revisions and the `X-Gameday: 1` header. Do not touch settings or adapters.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
