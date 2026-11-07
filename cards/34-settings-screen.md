# Card: Settings screen (delay)

**Target files:** app/web/status.html, tests/test_web_status.py
**Goal:** A `Settings` screen (`#/settings`) where the household sets the broadcast delay, saved through the `household` section. It also lays down the small shared pieces the Effects and Advanced screens reuse.
**Contract:**
- Nav gains `Settings` after `Teams`; `showView` handles `#/status`, `#/teams`, `#/settings` (and the next two cards' routes by adding to one route table, not more if/else); unsaved edits on any screen survive navigating away and back
- Delay: number input plus slider, 0 to 180 s in 1 s steps, shown as seconds with a one-line explanation ("how long after ESPN reports a score before the lights fire; streams run behind live"); the saved value is the default for every game
- Shared helper `sectionEditor(section)` used by this and the next two screens: load from `GET /api/settings`, hold a draft, Save/Discard bar, `PUT /api/settings/{section}` with `If-Match` and `X-Gameday`; 200 refreshes; 422 shows each message under its field (`error_location` already maps to section field names); 409 says it changed elsewhere and offers "Load latest"; leave-page warning while any screen is dirty
- The Teams screen keeps its own code (do not rewrite it); the header's `delay Ns` meta refreshes after a save
- Text via `textContent`; keyboard usable; works at phone width
**Done when:** `uv run pytest` and `uv run ruff check` pass; the flow checked in a browser against a live instance (save, 422 on a negative delay, 409 from a second tab); only the target files changed.
