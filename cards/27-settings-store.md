# Card: settings tables

**Target files:** app/store.py, tests/test_store.py
**Goal:** Persist editable settings sections with optimistic revisions and a change history.
**Contract:**
- Schema v3 (`PRAGMA user_version`): `settings(section PK, revision, value JSON, updated_at)` and `settings_history(id, section, revision, value JSON, changed_at, source)`; existing databases migrate on open
- `get_setting(section) -> (revision, value) | None`; `all_settings() -> {section: (revision, value)}`
- `put_setting(section, value, expected_revision, source, now, history_value=None) -> new_revision`: atomic; `expected_revision` 0 means "must not exist yet"; a stale revision raises `RevisionConflict(current_revision)` and writes nothing; the history row stores `history_value` when given (the caller passes a secrets-free copy)
- `settings_history(limit=50, section=None)` newest first
- A database file is created readable only by its owner, and an existing one with group/other access is tightened to 0600 (it will hold bulb signing keys)
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
