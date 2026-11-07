# Card: Schedule for multiple teams

**Target files:** app/web/status.py, app/web/status.html, tests/test_web_status.py
**Goal:** The Schedule card works for several followed teams: each row says which team's schedule it belongs to, and a filter shows one team at a time.
**Contract:**
- A team is identified by `(league, abbr)` (PIT is both the Steelers and the Penguins). `/api/status.teams` gains `key` (`league:ABBR`), `label` (the abbreviation, plus the league only when the abbreviation is ambiguous among followed teams) and `color` (the team's configured color as hex, or null)
- `schedule` has one row per followed team in each game, from that team's side (`team_key`, `us`, `opp`, `result`); two followed teams playing each other give two rows, one on each schedule. A game with no team data stays one row with `team_key` null
- The scoreboard's `us` flag also uses `(league, abbr)`
- Page: Team column and filter buttons ("All teams" plus one per team, remembered in localStorage when available) only when 2+ teams are followed; the next unplayed game of each visible team is highlighted
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser with two real teams; only the target files changed.
