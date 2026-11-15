# Card: Govee restore is verified

**Status:** done 2026-11-08 (awaiting review)
**Target files:** app/bulbs/govee.py, tests/test_bulbs_govee.py (the only files to edit)
**Goal:** A restore that the strip did not take is repeated, so an effect can never leave the strip bright for the evening.

## Contract
- Seen on game day 2026-11-08: after one celebration the strip stayed at 100% instead of returning to 1%. The log showed no error: Govee LAN commands are plain UDP with no acknowledgement, so a dropped or ignored command is silent. Cause not proven; the likeliest is a restore sent while the strip was still leaving streaming mode
- After streaming, wait 0.3 s (the same settle time used when entering the mode) before anything else is sent
- `restore()` sends the restore, waits 0.3 s, reads the strip back and compares on/off, brightness (within 1) and color (within 2) or white temperature; up to 3 tries in all, clearing the cached state before each repeat so every command is re-sent; a warning per miss and an error if it never confirms
- Cost: about 0.6 to 0.9 s more per effect on the strip

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed
