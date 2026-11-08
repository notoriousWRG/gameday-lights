# Card: effect settings shape and validation

**Status:** done 2026-11-08 (G16, awaiting review)
**Target files:** app/config.py, app/settings.py, tests/test_config.py, tests/test_settings.py
**Goal:** Config and the stored `effects` section can express the fixture and team x fixture layers, validated with the same rules as the TOML seed.

## Contract
- TOML: `[effects.score]` (global, as today); `[effects.fixtures.<bulb>]` (fixture layer); per team `effects = {...}` and `fixture_effects.<bulb> = {...}` (team layers)
- Every layer takes `kind` plus the kind's params and `color`, `alt_color`; unknown field is a `ConfigError` naming the path
- A layer naming an unknown bulb, or a kind the bulb's `kind` does not support, is a `ConfigError`
- Existing configs and stored settings load unchanged; `sections_from_config` and TOML export/import round-trip the new layers

## Constraints
- Do not change how other fields validate. Do not touch main.py, dispatcher or web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] An old stored `effects` section loads as the global layer only
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
