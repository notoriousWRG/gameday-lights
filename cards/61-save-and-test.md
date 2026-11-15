# Card: Save and test in one step

**Status:** done 2026-11-08 (awaiting review).
**Target files:** app/web/status.html, tests/test_web_status.py (the only files to edit)
**Goal:** Editing then testing is one flow, not two: no hunting for a distant Save button.

## Contract
- Every editor's save bar becomes sticky at the bottom of the screen while there are unsaved changes
- Test buttons that are disabled while a draft is unsaved become "Save & test": they save, then test, and show the result in the same place (Effects Try-it, each matrix cell, Teams)
- A cell shows a small "Unsaved" tag instead of the long note
- A save error leaves the test unplayed and shows the error where the field is

## Constraints
- Reuse `edSave`; do not change server endpoints. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
