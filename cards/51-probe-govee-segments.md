# Card: Govee per-segment probe

**Target files:** scripts/probe_govee_segments.py, tests/test_probe_govee_segments.py (the only files to edit)
**Goal:** Find out whether the user's strip (H616D) accepts Govee's reverse-engineered "razer" streaming mode, how many segments it has, and whether a green/gold chase can walk down it without a fade.

## Context to read (read-only)
- app/bulbs/govee.py: `GoveeBulb`, `UdpTransport` (send), `GoveeSnapshot`
- scripts/probe_govee.py: flags and restore pattern this mirrors
- DECISIONS.md: "One project" section, open questions on the flash cap and segments

## Contract
- Packet: `BB 00 <size> <command> <data...> <checksum>`, size = len(data), checksum = XOR of every earlier byte, sent base64 in `{"msg":{"cmd":"razer","data":{"pt":"<b64>"}}}` to ip:4003
- Enable `0xB1` data `[1]` (known good: `uwABsQEK`); disable `0xB1` data `[0]`; LED data `0xB0` data `[0 (discrete), count, r,g,b ...]`
- `build_packet(command, data) -> bytes`, `razer_message(packet) -> dict`, `chase_frame(n, offset, chunk, colors) -> list[Color]`
- `uv run python scripts/probe_govee_segments.py --ip IP [--segments N] [--chunk 5] [--speed 10] [--seconds 8]`
- Always: disable razer mode and restore the snapshot in `finally`; the device also times out of the mode after about a minute
- Chase speed (pixels per second) divided by chunk length must stay at or under the flash cap (2 color changes per pixel per second); refuse otherwise

## Constraints
- Reuse `GoveeBulb` for snapshot/restore and `UdpTransport` for sending. No changes to app/.
- Tests use a fake transport; no network.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Tests: `build_packet` reproduces `uwABsQEK` for enable; chase frames rotate and wrap; the cap check refuses a too-fast chase
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
