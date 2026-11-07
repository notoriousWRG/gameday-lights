# Card: settings API

**Target files:** app/web/status.py, app/settings_service.py, app/main.py, tests/test_web_settings.py
**Goal:** HTTP endpoints to read and edit the stored settings, built on `SettingsService`; no screens yet.
**Contract:**
- `GET /api/settings` -> `{sections: {name: {revision, value}}, machine: {dispatch_enabled, db_path, web}}`; bulb signing keys never appear (`has_signing_key` instead); `machine` is read-only information
- `PUT /api/settings/{section}` with body `{"value": ...}`, header `If-Match: <revision>` and `X-Gameday: 1`: 200 `{revision, value, applied: true}`; 400 bad JSON/body/If-Match; 403 no `X-Gameday`; 404 unknown section (machine settings are not sections); 409 stale revision (with the current revision and value); 422 invalid `{errors: [{path, message}]}` (same rules as `config.toml`, unknown fields refused); 428 no `If-Match`
- `GET /api/settings/history?limit=&section=` -> newest first `{section, revision, source, changed_at, value}`, secrets-free
- An edit is live at once: the status API and components using the config provider see it with no restart
- Routes exist only when a `SettingsService` is passed to `create_app`
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
