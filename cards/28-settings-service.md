# Card: settings service

**Target files:** app/settings_service.py, tests/test_settings_service.py
**Goal:** Own the stored settings: seed them from `config.toml` on first start, hold the current `Config` snapshot, apply validated edits, and export back to TOML.
**Contract:**
- `SettingsService(store, machine_raw, base_dir, now=utc_now)`; `seed(cfg, force=False) -> [sections written]`: a missing section is imported from the TOML-derived config at revision 1; with `force` differing sections are overwritten (history source `config import`); `diverged(cfg) -> [sections]` for the startup warning
- `load()` builds the snapshot from stored sections (raises `ConfigError` if stored data is invalid); `config` property; `sections()` (internal, with secrets) and `public_sections()` (`{section: {revision, value}}`, signing keys redacted)
- `update(section, value, expected_revision, source="ui") -> (revision, config)`: strict shape check, the whole new config validated (cross-section rules) before anything is written, then written with the revision check, then the snapshot swapped and subscribers called `(old, new)`; a no-op edit writes nothing; refused edits change nothing. `ConfigError` -> 422 material, `RevisionConflict` -> 409 material
- Bulb signing keys: an incoming bulb without `signing_key` keeps its stored key (matched by name); `null` or `""` clears it; a string sets it; `has_signing_key` in the input is ignored; history rows never contain keys
- `export_toml(include_secrets=True)` returns TOML that `load_config` reads back to an equal `Config`
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
