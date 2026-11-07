# Card: page navigation and Teams screen

**Target files:** app/web/status.html, tests/test_web_status.py
**Goal:** A Teams screen to follow and unfollow teams, choose each team's bulbs and colors, and save, with the existing page becoming the Status view behind a small nav.
**Contract:**
- Nav: `Status` (default) and `Teams`, hash routes `#/status` and `#/teams`; the status refresh keeps running in the background
- Teams view: the followed teams (name when known, league, bulbs as checkboxes, color and alternate color pickers pre-filled from ESPN with a "Use ESPN's" reset and a warning for very dark colors, Remove); a "Follow a team" card (league, search box with debounce, results with a Follow button that is disabled for teams already followed); edits are a draft until Save
- Save: `PUT /api/settings/teams` with `If-Match` and `X-Gameday`; 200 refreshes the list and the status view; 422 shows each message under the team row it belongs to (`teams[i].field`) and anything else in a banner; 409 says the list changed elsewhere and offers "Load latest"; unsaved edits trigger the browser's leave-page warning
- Following needs at least one bulb (otherwise a clear message); a new team starts on the first bulb
- All text is inserted with `textContent`; keyboard usable; works at phone width
**Done when:** `uv run pytest` and `uv run ruff check` pass; every flow checked in a browser against a live instance; only the target files changed.
