# Decisions

Settled during planning (2026-11-06). Phase 0 results get appended by card C03.

| Topic | Decision |
|---|---|
| Scope | Phase 0 + Phase 1 only. Phase 2+ planned after the Phase 1 gate |
| Execution | Claude writes cards and executes them; stop for review after each card group |
| Card style | One card per module (module + its test file together); template says "Target files" |
| Tooling | uv + pyproject.toml + uv.lock (uv supplies Python 3.12); plain `pip install .` still works |
| Repo | Public GitHub, MIT license. No secrets committed: `config.toml` gitignored, `config.example.toml` committed |
| Bulb brand | WiZ only. LIFX dropped. Adapter interface stays brand-neutral |
| Bulb IP | Store the IP and MAC; if the IP stops answering, re-discover by MAC over broadcast |
| League | NFL only for probes, fixtures and tests; code stays league-agnostic, NHL is config later |
| Viewing | NFL+ cast to TV; first delay profile = "NFL+ cast" |
| Fixtures | Probe writes a response only when its content hash changes, gzipped: `tests/fixtures/<league>/<event_id>/NNNN_<ts>.json.gz` |
| Lag measurement | Keypress in the probe: press Enter when the score shows on TV; paired with the latest unpaired detected change and logged |
| Score firing | Every increase fires (TD +6 and PAT +1 are separate events); one effect type, `score`; delta and NFL label (TD/FG/safety/try) stored in `detail` |
| Decreases | Stored, nothing fires |
| Dedupe key | `(game_id, team_id, increase_n)`; per-team increase counter in SQLite that never decrements |
| Restart | First poll after process start is a baseline. Increases missed while down are recorded as `skipped_restart`, never fire (they still bump the counter) |
| Overlap | Per-bulb serial queue: next effect starts after the previous one restores |
| Flash cap | Hard code-level max 2 color changes/sec, enforced in pattern validation |
| Default effect | Slow pulse 5x, ~6 s, team color <-> alternate color (ESPN team data, overridable in config), then restore |
| Delay | Fixed default 45 s, in config |
| Guardrails | Only the flash cap in Phase 1 (brightness cap, quiet hours, kill switch/Hold arrive in Phase 2) |
| Config | TOML (stdlib `tomllib`) parsed into dataclasses |
| Scheduling | Plain asyncio tasks; injectable clock for tests |
| Phase 1 run | systemd --user unit on Pop!_OS; `dispatch_enabled = true` because it owns the WiZ bulb |

Unconfirmed defaults (object at review): ruff as linter; stdlib dataclasses over pydantic; ESPN CDN fallback deferred to Phase 2; schedule sync every 6 h; watch window opens 10 min before kickoff; poll 15 s live and 60 s during halftime/breaks; all times UTC.
