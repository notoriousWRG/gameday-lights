# Card: systemd user unit and run docs

**Target files:** deploy/systemd/gameday-lights.service, README.md
**Goal:** Run gameday-lights unattended on Pop!_OS as a systemd --user service, documented.

## Contract
- Unit runs `.venv/bin/gameday-lights --config config.toml run` from the repo directory, restarts on failure, starts at login (or boot with linger)
- README documents setup, the WiZ "only allow verified controls = off" requirement, `test-effect`, `run --replay`, logs and the Phase 1 gate check

## Done when
- [ ] `systemd-analyze --user verify` accepts the unit (if available)
- [ ] Only the target files changed
