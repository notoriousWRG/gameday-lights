# Card: Practice mode on the Calibrate screen

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/web/static/screens.js, app/web/status.html, tests/test_web_calibration.py (the only files to edit)
**Goal:** On game day, switch practice on, press "I see it on TV" as each play shows up, and take the result as a starting delay before the first score.

## Context to read (read-only)
- app/web/static/screens.js: the Calibrate screen and its "I see it on TV" buttons, `by_label` table
- Cards 80 and 81: the `plays` list, `by_label["Play"]`, `/api/practice`

## Contract
- A **Practice mode** switch at the top of Calibrate, with "on until 8:14 PM" while active and a plain explanation: "Lists each play as it is detected. Press the button when you see the same play on TV. Lights do not flash for plays."
- Disabled with the reason shown when the API says no game is in its window
- While on, play rows (newest first) show the situation text, quarter and clock, the detected time, and an **I see it on TV** button; after a press the row shows its lag and a clear control. Rows poll with the page's existing refresh (no faster than the poll interval)
- A **Plays** group beside the score kinds: count, median, suggestion, and **Use as starting delay** that saves the suggestion as the general delay (the same save path and `If-Match` as Settings). It does not touch per-kind delays, and its confirmation says that a first real score should still be marked to fine-tune
- Below three marked plays the group says "mark a few more plays" and shows no suggestion
- Text explains the caveat once: plays get you close; touchdowns and extra points can differ by a few seconds

## Constraints
- Plain JS in the existing static files; no new library
- No new hard-coded timing: the refresh uses the interval the page already has

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] The served page contains the switch, the Plays group and the button (page-text test)
- [ ] In dry-run with a faked board: switch on, a play row appears, pressing the button shows a lag, three presses show a suggestion, the button saves it and Settings shows the new delay
- [ ] Only the target files changed
