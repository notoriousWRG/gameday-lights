# Card: Govee LAN adapter

**Target files:** app/bulbs/govee.py, tests/test_bulbs_govee.py (the only files to edit)
**Goal:** A `GoveeBulb` adapter and `discover_govee()` that speak Govee's LAN API (UDP) so a Govee strip (first target: H616D at a static IP) can be driven like any other bulb.

## Context to read (read-only)
- app/bulbs/base.py: `BulbAdapter`, `Color`, `Sleep`
- app/bulbs/wiz.py: shape to mirror (`BulbUnreachable`, snapshot dataclass, `discover_*` returning `[{"ip","mac"}]`)
- DECISIONS.md: "Bulb brand" row (updated by this group)

## Contract
- Protocol: JSON over UDP. Commands go to `ip:4003`. Replies (`scan`, `devStatus`) arrive unicast on local port 4002. Discovery sends `scan` to multicast `239.255.255.250:4001`.
- Messages: `turn` `{"value":0|1}`; `brightness` `{"value":1..100}`; `colorwc` `{"color":{"r","g","b"},"colorTemInKelvin":0}`; `devStatus` `{}`. All wrapped as `{"msg":{"cmd":..., "data":...}}`.
- `GoveeBulb(name, ip, mac=None, port=4003, sleep=..., transport=None)`: `set_color(color, brightness 1..255)` maps brightness to 1..100, turns the strip on if not known on, sends brightness only when it changed
- `snapshot()` returns `GoveeSnapshot(on, rgb, brightness, colortemp)` from `devStatus`; `restore()` turns off if it was off, else restores color (or color temperature when `colortemp > 0`) and brightness
- `ping()` is one `devStatus` round trip, seconds or `None`; never changes the strip
- No reply within a timeout (default 2 s, one retry) raises `BulbUnreachable` (import from `app.bulbs.wiz`)
- `discover_govee(wait_time=3, ...) -> list[dict]`: `[{"ip","mac"}]`, MAC lowercased without colons, sorted by IP, deduped. Govee's 8-byte device id is stored as the `mac` field, lowercased, colons removed.
- Anything that binds port 4002 (status, ping, discover) is serialized by one module-level lock, since replies are unicast to a shared port.
- Scenes, music and DIY modes are not reported by `devStatus` and cannot be restored; document this in the module docstring.

## Constraints
- No network in tests: inject a fake transport. Port numbers and timeouts are constructor/args with these defaults, not scattered literals.
- Do not touch `base.py`, `wiz.py` or other files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Fake-transport tests cover: set_color packets and brightness mapping, snapshot/restore (on, off, color temp), ping, timeout -> `BulbUnreachable`, discover dedupe/sort
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
