# Card: Saved light scenes (settings shape)

**Status:** drafted 2026-11-08
**Target files:** app/config.py, app/settings.py, tests/test_config.py, tests/test_settings.py (the only files to edit)
**Goal:** Named scenes (for example "Game time", "Movie") store a state per bulb in settings, validated like everything else. OPTIONAL: start only when the Lights screen is in use.

## Contract
- TOML `[[scenes]]` with `name` and `[scenes.bulbs.<bulb>]` (`on`, `color` or `color_temp_k`, `brightness`); new settings section `scenes`
- Unknown bulb, both color and temperature, or out-of-range values are `ConfigError`s naming the path; old settings load with no scenes
- Round-trips through export/import (settings_service export is a follow-up in card 60)

## Constraints
- Do not touch dispatcher or web files. Follow CLAUDE.md.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
