# Card: WiZ discovery helper

**Target files:** app/bulbs/wiz.py, tests/test_bulbs_wiz.py
**Goal:** One adapter-level function that finds WiZ bulbs on the LAN, so the web app (and the CLI) never touch pywizlight directly.
**Contract:**
- `async def discover_wiz(broadcast="255.255.255.255", wait_time=5, discover=discover_lights) -> list[dict]` returns `[{"ip", "mac"}]` with the MAC lowercased and without colons, sorted by IP, duplicates by MAC removed
- Errors from the network layer surface as `BulbUnreachable` with a readable message (no raw tracebacks)
**Constraints:** tests use a fake `discover`; no network. Do not change `WizBulb`.
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
