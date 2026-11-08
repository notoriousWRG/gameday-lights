# Plan: Phase 0 + Phase 1

Each group ends with a review stop. Cards live in `cards/NN-<slug>.md`.

- [x] **G0 Bootstrap** (direct, no card): pyproject, uv.lock, .gitignore, LICENSE, CLAUDE.md, ARCHITECTURE.md, PLAN.md, DECISIONS.md, README.md, cards/TEMPLATE.md. Then the user runs git init + push.
- [x] **G1 ESPN probe**: C01 `scripts/probe_scoreboard.py`
- [x] **G2 Bulb probe**: C02 `scripts/probe_bulb.py`
- [ ] **Phase 0 field work (user)**: run C01 through a live Packers game on NFL+ cast, pressing Enter on each score; run C02. C03 (doc card) records results in DECISIONS.md. Gate: stable measured delay, bulb responds locally in < 1 s, pulse looks right in green/gold.
- [x] **G3 Detector**: C04 `app/espn/detect.py` (written early; re-check against the GB @ NE recording)
- [x] **G4 Foundations**: C05 `app/config.py` (+ `config.example.toml`); C06 `app/store.py`
- [x] **G5 ESPN**: C07 `app/espn/client.py`; C08 `app/espn/schedule.py`
- [x] **G6 Bulbs and effects**: C09 `app/bulbs/base.py`; C10 `app/bulbs/wiz.py`; C11 `app/effects.py`
- [x] **G7 Runtime**: C12 `app/dispatch/dispatcher.py`; C13 `app/watcher.py`
- [x] **G8 Ship it**: C14 `app/main.py`; C15 systemd unit + README run section; C16 sync ARCHITECTURE.md

- [x] **G9 Status page** (Phase 2, first piece): C18 `[web]` config; C19 store queries; C20 watcher stats + bulb `ping`; C21 `app/web/status.py`; C22 Pulse button; C23 consolidated Schedule card; C24 Scoreboard card; C33 next game per followed team; C25 multi-team Schedule

- [x] **G10 Settings foundation** (no UI): C26 `app/settings.py` shared validation for settings sections (TOML seed and API use the same rules); C27 `app/store.py` schema v3: `settings` (section, revision, JSON) and `settings_history`; optimistic revisions; C28 `app/settings_service.py`: seed from `config.toml` on first start, assemble the current `Config` snapshot, `config export`/`import`; C29 live apply: Watcher, Dispatcher, planner and web read a `ConfigProvider` instead of a fixed `Config`; followed teams and the bulb registry reconcile when settings change; C30 settings API: `GET /api/settings`, `PUT /api/settings/{section}` (`If-Match`, `X-Gameday`, 422 with field errors, 409 stale), `GET /api/settings/history`
- [x] **G11 Teams flow**: C31 `GET /api/teams/search?league=&q=` (ESPN team list, cached, colors included); C32 page nav and Teams screen: followed teams (remove, bulbs, colors), search and follow, save with field errors; following triggers a schedule sync, so the Schedule filter appears
- [x] **G12 Settings, Effects, Advanced screens**: C34 Settings screen (delay) and the shared `sectionEditor`; C35 Effects screen with the Test button (the Pulse path); C36 Advanced timings. Later: quiet hours, brightness cap, Hold (need new settings sections and dispatcher support, so they are their own group)
- [x] **G13 Bulbs screen**: C37 `discover_wiz` in the WiZ adapter; C38 `POST /api/bulbs/discover`; C39 Bulbs screen (discover, add by IP, signing key write-only, reachability, Ping & test, remove)
- [ ] **G14 Govee bulbs**: C40 `app/bulbs/govee.py`; C41 bulb `kind` in config/settings; C42 factory + combined discovery; C43 Bulbs screen `kind`
- [x] **G15 Govee probe** (2026-11-08): C44 `scripts/probe_govee.py`. Ran against the H616D at 192.168.0.27: LAN control answers, devStatus median ~32 ms, restore matches. Still needs the user's eyes: did the strip jump or fade between green, gold, red, white (the fade decides the effect catalog's limits)? Results are in DECISIONS.md
- [x] **G15b Govee segments probe** (2026-11-08): C51 `scripts/probe_govee_segments.py`. A 20-segment green/gold chase over the unofficial razer streaming mode looked good on the H616D; real segment count still to find
- [x] **G16 Per-fixture effects** (2026-11-08, awaiting review; chase verified on the real strip end to end): C45 adapter capabilities, `SegmentPattern`, Govee `play_segments`; C46 effect catalog (pulse, chase); C47 `resolve_effect` (global -> fixture -> team -> team x fixture); C48 config/settings shape (`segments`, `effects.fixtures`, team `effects`/`fixture_effects`, validated per team x fixture); C49 planner plays a pattern per bulb; plus C52 `make_bulb` segments wiring and C53 export/rename carry the layers. Not done: C50 Effects screen matrix, and the team Test button still plays a whole-fixture pulse
- [x] **G17 Effects matrix** (2026-11-08, awaiting review): C50 per team and bulb on the Effects screen: resolved summary with the layer each setting comes from, edit the team x fixture layer, per-cell Test. Checked in a browser in dry-run (422 over-cap message shown, save, summary refresh, Test)
- [x] **G17b Segments field** (2026-11-08): C54 Segments on the Bulbs screen; without it the matrix could never offer Chase from the UI

## Phase 1 gate
`systemctl --user enable --now gameday-lights`; a full Packers game runs unattended with correct fires, recorded detected->fired times, and nothing replayed after a deliberate mid-game restart.
