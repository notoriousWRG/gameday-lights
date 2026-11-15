# Card: Govee model defaults

**Status:** done 2026-11-08 (awaiting review). Note: `app/main.py` needed no change; `discover_all` already passes the extra fields through.
**Target files:** app/bulbs/govee.py, app/main.py, app/web/status.html, tests/test_bulbs_govee.py, tests/test_main.py (the only files to edit)
**Goal:** Discovering a Govee strip fills in its segment count so Chase works without any setup.

## Contract
- `discover_govee` also returns the device's `sku` (from the scan reply); `SKU_SEGMENTS` table in govee.py, starting with H616D = 20 (verified); unknown models default to 1
- `discover_all` and the discover API pass `sku` through; the Bulbs screen's "Find bulbs" result adds the bulb with that segment count
- Adding by IP: a "Look up model" step reads the device's sku and fills segments the same way; the field stays editable

## Constraints
- Only add table rows for models someone has verified. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
