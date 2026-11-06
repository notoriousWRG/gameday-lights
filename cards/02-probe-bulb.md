# Card: WiZ bulb probe

**Target files:** scripts/probe_bulb.py, tests/test_probe_bulb.py (the only files to edit)
**Goal:** A standalone Phase 0 script that finds (or is given) a WiZ bulb, prints IP/MAC/type, snapshots it, measures per-command round-trip time, runs the green/gold pulse, optionally runs a burst test, and always restores the bulb.

## Context to read (read-only)
- intent.md: "Smart bulbs", Phase 0 acceptance checks
- DECISIONS.md: Bulb IP, Flash cap, Default effect rows
- .venv/lib/python3.12/site-packages/pywizlight/bulb.py: `wizlight`, `PilotBuilder`, `updateState`

## Contract
- CLI: `uv run python scripts/probe_bulb.py [--ip IP] [--mac MAC] [--broadcast ADDR] [--signing-key HEX] [--rtt-count 10] [--burst] [--burst-rates 2,5,10] [--burst-count 20]`
- Without `--ip`, discover by UDP broadcast and use the first bulb (or the one matching `--mac`)
- Pure helpers (tested): `snapshot(state)`, `snapshot_to_pilot(snap)`, `pulse_steps(color_a, color_b, pulses, duration_s)`, `rtt_stats(samples)`
- Pulse default: 5 pulses over ~6 s, Packers green (0,160,60) <-> gold (255,182,18); steps never exceed 2 color changes/sec (asserted)
- Burst test is opt-in, asks for confirmation (rapid flicker warning), uses low-contrast brightness alternation, and reports sent / timed out / late (> 1 s)
- The bulb is restored in a `finally` block

## Constraints
- Standalone: pywizlight + stdlib only. Do not touch app/ or other scripts.

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] `--help` runs
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
