# Card: Score detector

**Target files:** app/espn/detect.py, tests/test_detect.py (the only files to edit)
**Goal:** Pure functions that find score changes for followed teams between two scoreboard responses. Pulled forward from G3 because the watcher (C13) needs it; to be re-checked against the recorded GB @ NE game.

## Context to read (read-only)
- tests/fixtures/nfl/: a real scoreboard response
- DECISIONS.md: Score firing, Decreases rows

## Contract
- `team_scores(scoreboard, followed_ids) -> list[TeamScore]` (game_id, team_id, abbr, score, state, status_name); scores may be strings or ESPN `{displayValue}` objects
- `detect(prev, curr, followed_ids) -> list[ScoreChange]`: `prev` may be None (then `[]`); includes decreases; a game or team absent from `prev` is a baseline, not a change; no change -> nothing
- `ScoreChange(game_id, team_id, abbr, old, new, state)` with `.delta`
- `score_label(league, delta)`: NFL 6 TD, 7 TD+PAT, 8 TD+2pt, 3 FG, 2 safety/2pt, 1 PAT; anything else `"score"`

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] TD then PAT across two polls gives two changes (+6, +1); a drop gives a negative delta
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
