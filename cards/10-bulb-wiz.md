# Card: WiZ adapter

**Target files:** app/bulbs/wiz.py, tests/test_bulbs_wiz.py (the only files to edit)
**Goal:** `WizBulb`, a `BulbAdapter` over pywizlight with snapshot/restore and MAC-based IP re-discovery.

## Context to read (read-only)
- app/bulbs/base.py: the interface
- scripts/probe_bulb.py: `snapshot`, `snapshot_to_pilot`, restore order (scene, rgb, color temp)
- DECISIONS.md: Bulb IP row. Bulb needs "only allow verified controls" OFF, or a `signing_key`

## Contract
- `WizBulb(name, ip, mac=None, port=38899, signing_key=None, light_factory=wizlight, discover=discover_lights)`
- On a `WizLightError` from any command: if `mac` is set, broadcast-discover, match the MAC, update `ip`, retry the command once; otherwise raise
- `snapshot()` returns a `WizSnapshot` dataclass; `restore()` turns the bulb off if it was off

## Constraints
- Tests use fake lights and a fake discover; no network.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A failing command followed by a discover that returns a new IP succeeds on retry at the new IP
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
