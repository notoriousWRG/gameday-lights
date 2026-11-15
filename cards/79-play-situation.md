# Card: Read the last play from the scoreboard

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/espn/schedule.py, tests/test_espn_schedule.py (the only files to edit)
**Goal:** A live game's parsed `situation` also carries what identifies one play, so the watcher can tell a new play from a repeat poll.

## Context to read (read-only)
- app/espn/schedule.py `_situation`, `parse_scoreboard_game`: today it keeps `text` (down and distance), `possession`, `possession_text`, `red_zone`
- app/watcher.py `_capture_live`: stores the parsed game per poll
- tests/fixtures/nfl/: no recorded live board exists, so fixtures for this card are hand-built from ESPN's shape and must be labelled as such

## Contract
- `_situation` adds `last_play`: `{"id": str | None, "text": str | None}` read defensively from `situation.lastPlay` (`id`, `text`); `None` when absent
- Also adds `clock` and `period` to the parsed game (from `status.displayClock` and `status.period`) if the game dict lacks them; they only label a play for the person watching
- Nothing else about the parse changes; a board without `lastPlay` still parses as before

## Constraints
- No new ESPN call and no change to `app/espn/client.py`
- Tests use fixtures only. A hand-built fixture is named `*_synthetic.json` and says so in a comment; replace it with a real recording after the next live game (see card 84)

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A board with `lastPlay` gives `last_play.id` and `.text`; one without gives `None`; a malformed `lastPlay` (a string, a list) does not raise
- [ ] Only the target files changed
