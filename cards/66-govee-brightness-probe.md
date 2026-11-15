# Card: Does streaming honor strip brightness?

**Status:** done 2026-11-08 (awaiting review). Note: the flag and its test are done; the live comparison needs the user's eyes on the strip and has NOT been run. Steps: set the strip to 40% on the Lights screen, run `uv run python scripts/probe_govee_segments.py --ip <ip> --brightness 40`, and say whether the chase is dimmer than at 100%.
**Target files:** scripts/probe_govee_segments.py, tests/test_probe_govee_segments.py (the only files to edit)
**Goal:** Find out whether the strip's device brightness applies during razer streaming, so chase is as bright as the user set. Needs the strip.

## Contract
- `--brightness N` (1..100) sets the device brightness before streaming; the user sets the strip to 100 then 40 and runs it
- Result is recorded in DECISIONS.md. If streaming ignores device brightness, `GoveeBulb.play_segments` scales RGB by the pattern brightness instead (small follow-up in govee.py)

## Constraints
- Do not change app/ files in this card. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
