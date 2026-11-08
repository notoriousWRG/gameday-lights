# Card: Segments field on the Bulbs screen

**Status:** done 2026-11-08 (found after G17: the strip offered no Chase because nothing in the UI could set `segments`)
**Target files:** app/web/status.html, tests/test_web_settings.py
**Goal:** A Govee bulb's segment count can be set on the Bulbs screen, and saving the Bulbs section never drops it.

## Contract
- Govee rows show a `Segments` number field (default 1) with a hint that Chase needs more than 1; WiZ rows have none
- `bulbPayload` always sends `segments` (1 for WiZ), so an unrelated edit does not reset a stored count
- New bulbs start at 1

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Browser check (dry-run): the strip offered only Pulse at 1 segment; after saving 20 it offered Chase and Pulse
- [x] Only the target files changed
