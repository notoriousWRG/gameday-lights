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
- [x] **G18 Lights control** (polish, game-time first): C55 adapters `set_state`/`current_state`; C56 dispatcher `set_state` through the bulb queue; C57 `GET/PUT /api/bulbs/{name}/state`; C58 Lights screen (on/off, brightness, color or white)
- [x] **G19 Flows and defaults** (C66's live strip comparison still to do by hand): C61 Save & test (sticky save bars); C62 Govee model defaults (discovery fills segments); C63 setup checklist and health banners; C64 effects screen layers and simpler matrix; C65 Teams Test plays real effects; C66 strip brightness probe (needs the strip)
- [x] **G20 Cleanup**: C67 shared color helpers; C68 retire the old single-pulse API (after C65); C69 split `status.py` by area; C70 split the page into static files (after C69); C71 shared test fixtures
- [ ] **G21 Docs**: C72 README, ARCHITECTURE, intent, DECISIONS, example config, CLAUDE.md rule, `docs/game-day.md`
- [ ] **G22 Scenes** (optional, after G18 is in use): C59 scenes settings shape; C60 apply and save scenes
- [x] **G23 Calibrate in the app** (2026-11-08, for game day): C73 `events.seen_at` (schema v4); C74 calibration endpoints; C75 Calibrate screen. Replaces the terminal probe for measuring lag
- [x] **G24 Game-day fixes** (2026-11-08, from the first live game; NOT yet deployed): C76 Govee restore verified and repeated; C77 a different delay per kind of score; C78 Calibrate and Settings per kind of score
- [x] **G25 Practice mode** (built 2026-11-15, awaiting review; C84 needs a live game, C85 is an idea; C79 read the last play from the scoreboard; C80 record plays while practice is on (never fires lights); C81 practice API and `plays` in the calibration data; C82 Calibrate screen switch, play rows, Plays group; C83 docs; C84 record a live board (needs a game; replaces the synthetic fixtures); C85 optional light cue (idea only)
- [x] **G26 Bulb moved** (2026-11-15, awaiting review; not deployed, browser check still to do; drafted after the strip's DHCP address changed .27 to .108): C86 Govee re-discovers by device id; C87 discovery shows a moved bulb and offers Update address; C88 a followed team may have no bulbs (clear, swap or mute lights); C89 a visible note on why Remove is greyed out. Build first: small, and G25 practice mode needs a reachable strip to test

- [x] **G27 Ready for others** (built 2026-11-15, awaiting review; C93 did not need watcher.py; polish still to do first: G26 browser check, C84 live board): C90 version + diagnostics API; C91 Diagnostics screen with Copy bundle; C92 heartbeat ping; C93 failure notifier
- [x] **G28 Portable runtime** (built 2026-11-15, awaiting review): C94 per-OS data dir; C95 `init` and `doctor`
- [ ] **G29 Installers**: C96 macOS/Linux bootstrap (launchd, systemd --user) built 2026-11-15, awaiting the Mac mini test (needs C101's release wheel, or `GAMEDAY_WHEEL`); C97 Windows bootstrap (Task Scheduler); C98 `update` command; C99 opt-in update-available note
- [ ] **G30 CI and releases**: C100 CI matrix (ubuntu/macos/windows); C101 tagged release workflow and `docs/releasing.md` (built 2026-11-15, untested on GitHub; needs a push and a tag)
- [ ] **G31 Docs site** (replaces G21/C72): C102 MkDocs + Pages deploy (built 2026-11-15, Pages not yet switched on); C103 install/setup/updating/troubleshooting pages (Mac-only so far: install-mac, first-setup, updating, troubleshooting; Windows and Linux pages wait for C97 and a Linux test); C104 sync README, ARCHITECTURE, DECISIONS, intent

## Phase 1 gate
`systemctl --user enable --now gameday-lights`; a full Packers game runs unattended with correct fires, recorded detected->fired times, and nothing replayed after a deliberate mid-game restart.
