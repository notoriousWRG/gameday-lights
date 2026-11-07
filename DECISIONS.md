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

## Editable settings and the UI (decided 2026-11-07)

| Topic | Decision |
|---|---|
| Storage | **Hybrid.** `config.toml` keeps the machine: `db_path`, `dispatch_enabled`, `[web]` enabled/host/port. Everything else is household state in the SQLite database: teams, bulbs, effects, delay, and the timings (poll, sync, watch lead, pulse cooldown, final hold) |
| `dispatch_enabled` | TOML only, never UI-editable: it is the per-instance safety that stops a dev machine from driving a bulb |
| Seeding | On first start with no stored settings, teams, bulbs, effects and timings are imported from `config.toml`, so existing configs keep working. After that the database wins; a differing TOML section is logged and ignored. `config export` writes the stored settings back to TOML; `config import --force` re-imports |
| Shape | One row per section (`teams`, `bulbs`, `effects`, `household`, `advanced`): validated JSON plus a revision. Edits send the revision they started from (`If-Match`); a stale one is refused (409), so two phones cannot overwrite each other. Change history is kept for review and revert |
| Validation | One set of rules shared by the TOML seed and the UI: flash cap, poll >= 10 s, bulbs referenced by teams must exist, colors. The 10 s poll floor holds even in the Advanced section |
| Live apply | Components read the current settings each poll or event (no restart). Edit = validate, save, swap the snapshot; effects already playing finish with the old values. Following a team triggers a schedule sync; adding a bulb creates its adapter and queue at runtime |
| Edit access | **Trust the LAN: no login.** The status page still binds to loopback by default, so editing is only possible from this machine until `[web].host` is set to a LAN address. Every write needs the `X-Gameday: 1` header (cross-site posts cannot send it) |
| Secrets | The bulb signing key is write-only through the API (never returned); the database file is created readable only by its owner |
| Timings in the UI | Editable under an Advanced section, same validation |
| Build order | Foundation (validation, settings store, live apply, settings API), then Teams, then Settings/Effects/Advanced, then Bulbs |

