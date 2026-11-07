# Card: store queries for the status page

**Target files:** app/store.py, tests/test_store.py
**Goal:** Read queries the status page needs.
**Contract:** `Store.recent_events(limit=25) -> list[Event]` (newest first); `Store.finished_games(limit=3) -> list[Game]` (status `post`, newest first). Existing behavior unchanged.
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
