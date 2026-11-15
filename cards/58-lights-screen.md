# Card: Lights screen

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/web/status.html, tests/test_web_status.py (the only files to edit)
**Goal:** A `Lights` screen (`#/lights`) to turn each bulb on or off and set its brightness and color or white temperature, for adjusting the room before a game.

## Contract
- One card per bulb: on/off switch, brightness slider, color picker, and a warm-to-cool white slider; shows the bulb's current state on load and every 10 s while the screen is open
- Changes apply when the control is released (not while dragging), at most one per 0.5 s per bulb; the 429 and 409 messages show on the card
- Strip: a hint that effects restore to whatever is set here
- Dry-run banner when nothing is sent

## Constraints
- Reuse `el`, `getJson` and the busy/dry-run state. No server changes. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
