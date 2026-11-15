# Card: Record a live board for the play fixtures (hand step)

**Status:** drafted 2026-11-09; needs a live game
**Target files:** scripts/record_board.py, tests/fixtures/nfl/ (new files only), tests/test_espn_schedule.py
**Goal:** Replace the synthetic play fixtures with real ESPN scoreboard captures, and confirm the play-change rule against them.

## Contract
- `scripts/record_board.py --league nfl --seconds N --every 15`: saves each distinct scoreboard JSON to `tests/fixtures/nfl/live_<game_id>_<n>.json` through `app/espn/client.py` (never a direct call); every interval is at least 10 s
- During a live game, run it for a few minutes. Then check, by hand: does `situation.lastPlay.id` exist, does it change exactly once per play, and does `situation.downDistanceText` change with it? Write what you find into DECISIONS.md
- If `lastPlay` is absent, change the card 80 rule to the text, period and clock fallback and say so

## Constraints
- Run only while a followed game is live; recorded files contain public scoreboard data only

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] The `*_synthetic.json` fixtures are replaced or kept with a note on how they differ from the recording
- [ ] The findings are in DECISIONS.md
