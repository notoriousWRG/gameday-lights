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

- [x] **G9 Status page** (Phase 2, first piece): C18 `[web]` config; C19 store queries; C20 watcher stats + bulb `ping`; C21 `app/web/status.py`; C22 Pulse button; C23 consolidated Schedule card; C24 Scoreboard card; C25 multi-team Schedule

- [x] **G10 Settings foundation** (no UI): C26 `app/settings.py` shared validation for settings sections (TOML seed and API use the same rules); C27 `app/store.py` schema v3: `settings` (section, revision, JSON) and `settings_history`; optimistic revisions; C28 `app/settings_service.py`: seed from `config.toml` on first start, assemble the current `Config` snapshot, `config export`/`import`; C29 live apply: Watcher, Dispatcher, planner and web read a `ConfigProvider` instead of a fixed `Config`; followed teams and the bulb registry reconcile when settings change; C30 settings API: `GET /api/settings`, `PUT /api/settings/{section}` (`If-Match`, `X-Gameday`, 422 with field errors, 409 stale), `GET /api/settings/history`
- [ ] **G11 Teams flow**: C31 `GET /api/teams/search?league=&q=` (ESPN team list, cached, colors included); C32 page nav and Teams screen: followed teams (remove, bulbs, colors), search and follow, save with field errors; following triggers a schedule sync, so the Schedule filter appears
- [ ] **G12 Settings, Effects, Advanced screens**: delay, effect pattern with the Test button (the Pulse path), Advanced timings; later quiet hours, brightness cap, Hold
- [ ] **G13 Bulbs screen**: discover, add by IP, name, signing key (write-only), ping and test

## Phase 1 gate
`systemctl --user enable --now gameday-lights`; a full Packers game runs unattended with correct fires, recorded detected->fired times, and nothing replayed after a deliberate mid-game restart.
