# Card: shared settings validation and section mapping

**Target files:** app/config.py, app/settings.py, tests/test_config.py, tests/test_settings.py
**Goal:** One validation path for the TOML file and for stored (UI-edited) settings, and a mapping between a `Config` and its stored sections.
**Contract:**
- `config.py`: `load_raw(path) -> (raw, base_dir)`; `parse_config(raw, base_dir) -> Config` (the existing validation, same messages); `load_config(path)` is unchanged for callers. A `None` color means "not set"
- `settings.py`: sections `bulbs`, `teams`, `effects`, `household` (`delay_s`), `advanced` (poll/sync/lead timings, `pulse_cooldown_s`, `final_hold_min`); everything else (`dispatch_enabled`, `db_path`, `[web]` enabled/host/port) is machine config, TOML only
- `sections_from_config(cfg) -> dict` (complete, normalized, JSON-safe; colors as `#rrggbb`); `machine_raw_from_config(cfg)`; `build_config(machine_raw, sections, base_dir) -> Config` using the same validation, rejecting unknown fields in a section; `redact(section, value)` hides bulb signing keys (`has_signing_key` instead)
- Round trip: `build_config(machine, sections_from_config(cfg)) == cfg`
**Done when:** `uv run pytest` and `uv run ruff check` pass; existing config tests unchanged and green; only the target files changed.
