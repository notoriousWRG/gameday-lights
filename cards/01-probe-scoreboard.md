# Card: ESPN scoreboard probe

**Target files:** scripts/probe_scoreboard.py, tests/test_probe_scoreboard.py (the only files to edit)
**Goal:** A standalone Phase 0 script that finds a team's game today, polls the ESPN scoreboard, logs score changes to CSV, saves changed responses as gzipped fixtures, and pairs Enter keypresses with detected changes to measure TV lag.

## Context to read (read-only)
- intent.md: "The data source" and "The delay problem"
- DECISIONS.md: Fixtures, Lag measurement rows
- CLAUDE.md: rules (never poll faster than 10 s)

## Contract
- CLI: `uv run python scripts/probe_scoreboard.py --team GB [--league nfl] [--interval 15] [--date YYYYMMDD] [--out probe_out]`
- Pure helpers (tested): `find_game(scoreboard, abbr)`, `scores(event)`, `content_hash(data)`, `diff_scores(prev, curr)`, `pair_press(changes, press_ts)`, `lag_summary(changes)`
- Fixtures: `tests/fixtures/<league>/<event_id>/NNNN_<ts>.json.gz`, written only when the content hash changes
- CSV `<out>/<league>_<event_id>_changes.csv`: detected_at, team, old, new, delta, pressed_at, lag_s
- Interval below 10 s is refused

## Constraints
- Standalone: only httpx + stdlib. Network only in `main`; helpers are pure.
- Do not touch: app/, other scripts

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] `--help` runs
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
