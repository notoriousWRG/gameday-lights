# Card: Govee strip probe

**Target files:** scripts/probe_govee.py, tests/test_probe_govee.py (the only files to edit)
**Goal:** A Phase 0 style probe that answers, for the user's Govee strip, the questions per-fixture effects depend on: does LAN control answer, how fast, what does `devStatus` report, does a color test change the strip, and does restore return it to the state it started in.

## Context to read (read-only)
- app/bulbs/govee.py: `GoveeBulb`, `UdpTransport`, `discover_govee`, `GoveeSnapshot`
- scripts/probe_bulb.py: the WiZ probe this mirrors (flags, output style, restore in `finally`)

## Contract
- `uv run python scripts/probe_govee.py [--ip IP] [--rtt-count N] [--no-color]`
- Without `--ip`, discover over multicast and use the only/first strip found; print every device found with its ip and id
- Prints, in order: the device; the raw `devStatus` data (every key, since unreported state cannot be restored); `devStatus` round-trip stats (n, min, median, p95, max) and the failure count; then, unless `--no-color`, a short green/gold/red/white test at the same brightness the app uses, one change per 0.6 s or slower; then restore and a second `devStatus` compared field by field against the first, printing MATCH or each differing field
- Pure helpers, testable without a network: `rtt_stats(samples) -> str` (same format as `probe_bulb.py`) and `diff_status(before: dict, after: dict) -> list[str]`
- Restore always runs in `finally`; if restore fails, say so and tell the user to reset the strip in the Govee Home app
- Exit code 0 on completion, non-zero if the device never answered

## Constraints
- Reuse `GoveeBulb` and `discover_govee`; do not write a second protocol implementation
- No burst test: fast flashing is not allowed (flash cap) and this card does not need it
- Tests use a fake transport; no network
- Do not touch app/ files

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] `rtt_stats` and `diff_status` have tests, and one test drives the probe flow with a fake transport (device found, status, color steps recorded, restore called last)
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
