# Game Lights: Phase 0 + Phase 1 build plan

## Context

`/home/wr/hack/game-lights` contains only `intent.md`. The goal is a home server that watches the Packers' games through ESPN's unofficial API and pulses a WiZ bulb in team colors when they score, timed to land with the (streamed, delayed) TV picture. This plan covers **Phase 0** (prove the pieces) and **Phase 1** (headless server MVP), built with the task-card workflow from `~/hack/greenAI/intent.md`. Claude writes each card and then executes it.

## Decisions settled in the grilling (go into DECISIONS.md)

| Topic | Decision |
|---|---|
| Scope | Phase 0 + Phase 1 only. Phase 2+ planned after the Phase 1 gate |
| Execution | Claude writes cards and executes them; **stop for review after each card group** |
| Card style | **One card per module** (module + its test file together). This departs from greenAI's single-target-file rule, so the template says "Target files" |
| Tooling | **uv + pyproject.toml + uv.lock** (uv supplies Python 3.12 on gift hosts, so recipients skip the Python installer step); plain `pip install .` still works |
| Repo | Claude creates files but does **not** `git init`; the user inits and pushes to a **public GitHub** repo before card 1 runs. **MIT** license. No secrets committed: `config.toml` gitignored, `config.example.toml` committed |
| Bulb brand | **WiZ only.** LIFX dropped (the LIFX acceptance check is struck). Adapter interface stays brand-neutral |
| Bulb IP | Unknown whether it's reserved, so store the IP **and MAC**; if the IP stops answering, re-discover by MAC over broadcast |
| League | **NFL only** for probes, fixtures and tests; code stays league-agnostic, NHL is config later |
| Viewing | NFL+ **cast to TV**; first delay profile = "NFL+ cast" |
| Fixtures | Probe writes a response **only when its content hash changes**, gzipped (`tests/fixtures/<league>/<event_id>/NNNN_<ts>.json.gz`) |
| Lag measurement | **Keypress in the probe**: press Enter when the score shows on TV; it is paired with the latest unpaired detected change and logged |
| Score firing | **Every increase fires** (TD +6 and the PAT +1 are separate events); one effect type, `score`; the delta and NFL label (TD/FG/safety/try) are stored in `detail` for later |
| Decreases | Stored, nothing fires (per intent) |
| Dedupe key | `(game_id, team_id, increase_n)`. A per-team increase counter in SQLite that never decrements, so a reversal followed by a re-score still fires |
| Restart | The first poll after process start is a **baseline**. Increases missed while down are recorded with status `skipped_restart` and never fire (they still bump the counter) |
| Overlap | Per-bulb **serial queue**: the next effect starts after the previous one restores |
| Flash cap | Hard code-level max **2 color changes/sec**, enforced in pattern validation; config cannot exceed it |
| Default effect | **Slow pulse 5×, ~6 s**, team color ↔ alternate color (from ESPN team data, overridable in config), then restore |
| Delay | Fixed default **45 s**, in config |
| Guardrails | None in Phase 1 besides the flash cap (brightness cap, quiet hours, kill switch/Hold arrive with Phase 2) |
| Config | **TOML** (stdlib `tomllib`), parsed into dataclasses |
| Scheduling | **Plain asyncio** tasks; injectable clock for tests |
| Phase 1 run | **systemd --user unit** on Pop!_OS; this instance has `dispatch_enabled = true` because it owns the WiZ bulb |

Choices I made that you haven't confirmed (object at review if needed): `ruff` as linter; stdlib dataclasses over pydantic for Phase 1; CDN fallback in the ESPN client deferred to Phase 2; schedule sync every 6 h; watch window opens 10 min before kickoff; poll 15 s live and 60 s during halftime/breaks (statuses from ESPN `status.type`); all times stored in UTC.

## Repo layout (end of Phase 1)

```
intent.md  CLAUDE.md  ARCHITECTURE.md  PLAN.md  DECISIONS.md  README.md  LICENSE
pyproject.toml  uv.lock  .gitignore  config.example.toml
cards/TEMPLATE.md  cards/NN-<slug>.md
app/config.py            # TOML → dataclasses (teams, bulbs, effects, delays, intervals, dispatch_enabled)
app/store.py             # SQLite: games, team_scores(score, increase_n), events(dedupe_key UNIQUE, detected_at, due_at, fired_at, status)
app/espn/client.py       # the ONLY ESPN caller: httpx async, TTL cache, timeout, exp. backoff
app/espn/detect.py       # pure: detect(prev, curr, followed_ids) -> list[ScoreChange]
app/espn/schedule.py     # pure: parse team schedule (regular + postseason) -> Game rows
app/bulbs/base.py        # BulbAdapter protocol (set_color, flash(pattern), snapshot, restore), Pattern + 2/s cap, DryRunBulb
app/bulbs/wiz.py         # pywizlight adapter, MAC re-discovery
app/effects.py           # effect config + team colors -> Pattern
app/dispatch/dispatcher.py  # delay wait, per-bulb serial queue, snapshot/restore, dry-run, logs fired_at
app/watcher.py           # schedule-sync loop + game-watcher loop, poll policy, baseline-on-start, event creation
app/main.py              # wiring + CLI: run | run --replay DIR | discover | test-effect
scripts/probe_scoreboard.py  scripts/probe_bulb.py
deploy/systemd/game-lights.service
tests/…  tests/fixtures/nfl/<event_id>/*.json.gz
```

Event shape follows the intent: `{game, team, type, detail, detected_at}` + `dedupe_key`, `due_at`, `fired_at`, `status` (logged for delay tuning).

## Card queue (each group ends with a review stop)

**G0: Bootstrap (Claude directly, no card; it's cross-file)**
pyproject (fastapi deferred; deps: httpx, pywizlight; dev: pytest, pytest-asyncio, ruff), `uv lock`, `.gitignore`, LICENSE (MIT), CLAUDE.md (intent's rules + exact commands `uv run pytest`, `uv run ruff check`, the stop-and-report rule), ARCHITECTURE.md, PLAN.md (this queue), DECISIONS.md (table above), README.md, `cards/TEMPLATE.md` (greenAI template, "Target files"). Requires installing uv on this box. → **You git init + push.**

**G1: ESPN probe.** C01 `scripts/probe_scoreboard.py`: auto-finds the team's game today, polls every 15 s, CSV of score changes with timestamps, gzip-on-change fixtures, Enter-key lag pairing, prints the lag summary on exit.

**G2: Bulb probe.** C02 `scripts/probe_bulb.py`: discover the WiZ bulb, print IP/MAC, snapshot, run the green/gold pulse, restore, per-command RTT, burst test (N commands at increasing rates → dropped/late count). Confirms port 38899 and the "allow local communication" toggle.

**Phase 0 field work (you):** run C01 through a live Packers game on NFL+ cast, pressing Enter on each score; run C02. C03 doc card records the results in DECISIONS.md. **Gate:** stable measured delay, bulb responds locally in < 1 s, and the pulse looks right in green/gold.

**G3: Detector.** C04 `app/espn/detect.py` + tests against the recorded game (incl. TD+PAT as two increases, and a decrease; synthetic fixture if the real game had none).

**G4: Foundations.** C05 `app/config.py` (+ `config.example.toml`); C06 `app/store.py` (schema via `PRAGMA user_version`, dedupe insert, increase counter).

**G5: ESPN.** C07 `app/espn/client.py` (tests via `httpx.MockTransport`; no network); C08 `app/espn/schedule.py`.

**G6: Bulbs and effects.** C09 `app/bulbs/base.py` (cap enforcement tests); C10 `app/bulbs/wiz.py` (mocked transport); C11 `app/effects.py`.

**G7: Runtime.** C12 `app/dispatch/dispatcher.py` (fake clock: delay, serial queue, restore-on-error, dry-run); C13 `app/watcher.py` (replay client drives a recorded game; restart mid-game → no replays).

**G8: Ship it.** C14 `app/main.py` + CLI smoke test; C15 `deploy/systemd/game-lights.service` + README run section; C16 doc card syncs ARCHITECTURE.md with the real tree.

## Verification

- Every card: `uv run pytest` and `uv run ruff check` pass; `git diff --stat` shows only the card's target files.
- Phase 1 offline: `uv run game-lights run --replay tests/fixtures/nfl/<event_id> --dry-run` replays the whole recorded game, and the log shows one effect per increase at detected_at + 45 s. Kill it and restart mid-replay: no duplicate fires (`status=skipped_restart` rows).
- `uv run game-lights test-effect score --team GB` pulses the real bulb and restores it.
- **Phase 1 gate:** `systemctl --user enable --now game-lights`; a full Packers game runs unattended. Afterward, the events table shows correct fires, detected→fired times, and nothing replayed after a deliberate mid-game `systemctl --user restart`.

## Handoff status (2026-11-06)

- Plan approved. Nothing built yet; the repo still has only `intent.md` and this file.
- G0 has not started. The `uv` install (`curl -LsSf https://astral.sh/uv/install.sh | sh`) was declined at the prompt, so ask the user how they want uv installed before continuing.
- Facts about this box: Python 3.12.3 is at /usr/bin/python3, but `ensurepip`/`pip` are missing and uv and docker are not installed.
- The card template and workflow come from `~/hack/greenAI/intent.md`, section "Working model: I orchestrate, the agent executes cards" (template at lines ~78–105).
- Do not `git init`; the user does that after G0. Stop for review after each card group.
