# Card: Say why a bulb cannot be removed

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/web/static/screens.js, app/web/static/status.css, tests/test_web_status.py (the only files to edit)
**Goal:** A greyed-out Remove button on the Bulbs screen comes with a visible note saying which teams use the bulb and a link to fix it, not only a hover tooltip (which phones never show).

## Context to read (read-only)
- app/web/static/screens.js ~line 728: `rm.disabled = users.length > 0` and the tooltip
- app/web/static/nav.js: how a screen is opened by name

## Contract
- The Remove button stays greyed out while any team lists the bulb
- Under the bulb's row head, a small line reads "In use by GB, MIN. Take it off those teams to remove it." with **Teams** as a link to the Teams screen; the tooltip text stays too
- The line shows only while Remove is disabled and counts unsaved edits (same source as now: the draft teams)
- Keep the greyed button in the layout (do not hide it), with `aria-describedby` pointing at the note

## Constraints
- No new API; the data is already on the screen
- Keep text and colors in the existing note style (`warn`/`pill` classes)

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] The page-contains checks cover the note text and the Teams link
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
