# Card: Bulbs screen and discover API carry `kind`

**Target files:** app/web/status.py, app/web/status.html, tests/test_web_settings.py
**Goal:** `POST /api/bulbs/discover` passes through each result's `kind`; the Bulbs screen shows it, adds discovered bulbs with it, offers a kind choice when adding by IP, and defaults the port by kind.

## Contract
- Discover result becomes `[{ip, mac, kind, known, name}]`; a missing `kind` from the callable reads as `"wiz"`
- `bulbPayload` sends `kind`; the add form has a kind select (WiZ / Govee); blank port means 38899 (wiz) or 4003 (govee)

## Constraints
- Existing behavior for WiZ unchanged. Do not touch other files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed
