# Card: next game for every followed team

**Target files:** app/web/status.py, app/web/status.html, tests/test_web_status.py
**Goal:** The Scoreboard shows the next unplayed game for each followed team (up to 3), not just the soonest one.
**Contract:**
- `scoreboard.next_games`: for each followed team its first game that has not started (and is not already on the card), soonest first, at most `MAX_NEXT_GAMES` (3); a game two followed teams share appears once, on the team earlier in the list; each entry is a schedule row plus `in_week` (kickoff within 7 days). Replaces `next` and `next_in_week`
- No live, pre-game or just-finished game: one card per next game (team, matchup, day and time, live countdown, and a label: TONIGHT, TOMORROW, THIS WEEK or NEXT GAME). While a game is shown, the other teams' next games appear as "Next up" lines under it
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser with two teams; only the target files changed.
