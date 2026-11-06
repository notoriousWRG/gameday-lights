# Plan: Phase 0 + Phase 1

Each group ends with a review stop. Cards live in `cards/NN-<slug>.md`.

- [ ] **G0 Bootstrap** (direct, no card): pyproject, uv.lock, .gitignore, LICENSE, CLAUDE.md, ARCHITECTURE.md, PLAN.md, DECISIONS.md, README.md, cards/TEMPLATE.md. Then the user runs git init + push.
- [ ] **G1 ESPN probe**: C01 `scripts/probe_scoreboard.py`
- [ ] **G2 Bulb probe**: C02 `scripts/probe_bulb.py`
- [ ] **Phase 0 field work (user)**: run C01 through a live Packers game on NFL+ cast, pressing Enter on each score; run C02. C03 (doc card) records results in DECISIONS.md. Gate: stable measured delay, bulb responds locally in < 1 s, pulse looks right in green/gold.
- [ ] **G3 Detector**: C04 `app/espn/detect.py`
- [ ] **G4 Foundations**: C05 `app/config.py` (+ `config.example.toml`); C06 `app/store.py`
- [ ] **G5 ESPN**: C07 `app/espn/client.py`; C08 `app/espn/schedule.py`
- [ ] **G6 Bulbs and effects**: C09 `app/bulbs/base.py`; C10 `app/bulbs/wiz.py`; C11 `app/effects.py`
- [ ] **G7 Runtime**: C12 `app/dispatch/dispatcher.py`; C13 `app/watcher.py`
- [ ] **G8 Ship it**: C14 `app/main.py`; C15 systemd unit + README run section; C16 sync ARCHITECTURE.md

## Phase 1 gate
`systemctl --user enable --now game-lights`; a full Packers game runs unattended with correct fires, recorded detected->fired times, and nothing replayed after a deliberate mid-game restart.
