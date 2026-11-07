# Card: team search endpoint

**Target files:** app/espn/schedule.py, app/web/status.py, app/main.py, tests/test_espn_schedule.py, tests/test_web_settings.py, tests/fixtures/teams/
**Goal:** The data the Teams screen needs to find and follow a team: leagues, and a searchable ESPN team list with colors.
**Contract:**
- `parse_team_list(data) -> [{id, abbr, name, short_name, color, alt_color}]` (pure): active teams only, sorted by name, colors as `#rrggbb` or null
- `GET /api/leagues` -> `[{key, label}]` for the leagues the client supports
- `GET /api/teams/search?league=&q=` -> up to 50 matches (every word of `q` must appear in the team name or abbreviation, case-insensitive; empty `q` lists all), each with `league` and `followed` (true when in the current settings); 400 for an unknown league; 502 with the reason when ESPN fails
- Goes through `EspnClient.teams` (cached 24 h); the routes exist only when an ESPN client is passed to `create_app`
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
