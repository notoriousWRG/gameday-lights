# Card: `init` and `doctor` commands

**Target files:** app/main.py, app/doctor.py (new), app/starter.toml (new, packaged with the app), tests/test_doctor.py, tests/test_paths.py (new), tests/test_main.py
**Goal:** `gameday-lights init` creates the data dir and a starter `config.toml` (idempotent, never overwrites) and prints the web address. `gameday-lights doctor` prints pass/fail lines: config valid, data dir writable, port free, can reach ESPN, UDP broadcast socket opens, each saved bulb answers, plus the OS firewall hint (Windows prompt, macOS "local network" permission) when discovery finds nothing.

## Constraints
- Default `[web] host` stays loopback; init asks nothing and doctor says how to open it to the LAN (`host = "0.0.0.0"` is not allowed to be bound outside the LAN: keep the existing rule, suggest the machine's LAN address).
- ESPN reach goes through `app/espn/client.py`.

## Done when
- [ ] pytest and ruff pass; init twice leaves the first file untouched (tested)
