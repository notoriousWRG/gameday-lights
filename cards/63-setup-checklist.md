# Card: Setup checklist and health banners

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/web/status.py, app/web/status.html, tests/test_web_status.py (the only files to edit)
**Goal:** A new install tells the user what is left to do; a running one says what is wrong.

## Contract
- `GET /api/setup` returns checklist items: a bulb is added; a team is followed; every followed team has a bulb; each bulb answers; dispatch is live or dry-run; with a `fix` link (`#/bulbs`, `#/teams`) for each
- Status page shows the unfinished items as a short list at the top (hidden when all done); an unreachable bulb shows a banner on Status and Lights
- Empty states on Teams, Bulbs and Effects say what to do first, with a button

## Constraints
- No new settings. Do not change existing endpoints. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
