# Decisions

Settled during planning (2026-11-06). Phase 0 results get appended by card C03.

| Topic | Decision |
|---|---|
| Scope | Phase 0 + Phase 1 only. Phase 2+ planned after the Phase 1 gate |
| Execution | Claude writes cards and executes them; stop for review after each card group |
| Card style | One card per module (module + its test file together); template says "Target files" |
| Tooling | uv + pyproject.toml + uv.lock (uv supplies Python 3.12); plain `pip install .` still works |
| Repo | Public GitHub, MIT license. No secrets committed: `config.toml` gitignored, `config.example.toml` committed |
| Bulb brand | WiZ first. LIFX dropped. Adapter interface stays brand-neutral. Govee LAN API added 2026-11-07 (user's H616D strip); each bulb has a `kind` |
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


## One project: per-fixture, per-team effects (decided 2026-11-08)

| Topic | Decision |
|---|---|
| Direction | **One project.** No separate controller repo. The per-fixture, per-team effect controls gameday needs are the same fixtures, effects, resolution and settings UI a generic controller would need, so they are built here. The name stays gameday-lights |
| Scope | Gameday-driven only for the next milestones. Scenes, schedules, an arbiter, MQTT and sensor triggers wait until a second real use needs them. The layers stay in their own modules (`app/bulbs/`, `app/effects.py`, the settings core) so they can be split out later |
| Effect model | A **catalog of effect kinds with parameters** (pulse first; breathe, chase, sparkle to follow). Overrides layer global -> fixture -> team -> team x fixture, each layer optional. A fixture offers only the kinds its adapter supports |
| Gift installs | Unchanged: one bulb, one default effect, no matrix unless more fixtures are added. A recipient never has to see the generic parts |
| Govee probe (C44, 2026-11-08) | H616D strip at 192.168.0.27, LAN control on. `devStatus` reports onOff, brightness, color, colorTemInKelvin only (no scene/mode), median round trip ~32 ms, p95 ~470 ms. Restore from a solid red 100% strip matched the start exactly. Not yet verified: fade between colors, and restore from a scene or music mode (devStatus cannot report those) |

Open (the next card group is blocked on these):
- **Decided 2026-11-08: the flash cap is per segment.** A fixture-wide flash is still capped at 2 color changes/sec. For a chase, a segment changes color once per `chunk` segments of travel, so `speed / chunk` must be at most 2 per second per segment, enforced in code like the existing cap (config cannot exceed it). Fades and breathe still need a separate brightness-change rule before they ship
- **Flash cap vs smooth effects (superseded for chase by the line above; still open for fades/breathe).** The cap is "2 color changes/sec". A breathe or fade is many small changes per second and a chase is many segments. Does the cap become a limit on high-contrast flashing only, or on luminance change per second? It is a photosensitivity rule, so it needs an explicit decision before any non-pulse effect ships
- **Segment pattern type.** `Pattern` is whole-fixture color; a chase needs a per-segment frame type (list of colors per frame). Card 46 adds it, after the flash-cap decision

Segment count: 20 segments covers the whole H616D strip (user confirmed 2026-11-08, chase reaches both ends and wraps). Treat the count as a per-fixture setting, default 1 (whole fixture), 20 for this strip.

Verified end to end (2026-11-08): a scored event through the planner, dispatcher and `GoveeBulb.play_segments` ran an 8 s green/orange chase on the H616D (20 segments, whole strip) and restored it; the user confirmed it looked right. Not yet checked: device brightness below 100% during streaming.

Resolved by the probes (2026-11-08):
- **Govee fade.** The strip fades between normal `colorwc` commands (user observed, quick fade); the firmware fade cannot be shortened, so a pulse on the strip reads as a glow
- **Per-segment control works on the H616D** through the unofficial "razer" streaming mode (C51): packet `BB 00 <size> <cmd> <data> <xor>` base64 in a `razer` message to port 4003, enable `B1`, LED data `B0`. A green/gold chase of 4-segment chunks at 4 segments/s looked good, with no fade. Streaming applies instantly, drops back to normal after about a minute without frames, and hides app scenes while active. Gold `(255, 140, 0)` reads better than `(255, 182, 18)`, which washed toward white
- **Restore from scenes.** A strip left in a scene or music mode comes back as a plain color
- **Per-team colors per fixture.** Layer it in, or leave it out of the first cut
