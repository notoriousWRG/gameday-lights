# Card: ESPN schedule and team parsing

**Target files:** app/espn/schedule.py, tests/test_espn_schedule.py (the only files to edit)
**Goal:** Pure functions turning ESPN schedule and team JSON into `Game` rows and team colors.

## Context to read (read-only)
- tests/fixtures/nfl_schedule/: real GB regular-season schedule, empty postseason response, team response
- app/store.py: `Game`

## Contract
- `parse_schedule(data, league) -> list[Game]`: `game_id` = event id, `name` = shortName, `start_utc` tz-aware UTC, `status` = ESPN state (`pre`/`in`/`post`)
- Events with `timeValid` false (placeholder kickoff time) are skipped; they appear once ESPN sets a time
- `merge_schedules(*games_lists)` dedupes by game id (later wins)
- `parse_team_colors(team_data) -> (primary, alternate)` as RGB tuples from ESPN's hex `color`/`alternateColor`

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] The real fixture parses: 17 events minus any with an invalid time
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
