# Card: export and rename carry effect layers

**Status:** done 2026-11-08 (added during G16; not in the original draft)
**Target files:** app/settings_service.py, tests/test_settings_service.py
**Goal:** `config export` writes the team and fixture effect layers as TOML tables that load back equal, and renaming a bulb renames its keys in `teams[].fixture_effects` and `effects.fixtures`.

## Contract
- Export writes `[teams.effects]`, `[teams.fixture_effects."<bulb>"]` after each team and `[effects.fixtures."<bulb>"]` after `[effects.score]`; bulb names are always quoted keys
- `rename_bulb` also rewrites the `effects` section. Its revision is the stored one (not checked against the caller's), because the caller only holds the bulbs and teams revisions

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Export then load gives an equal Config; a renamed bulb keeps its layers under the new name
- [x] Only the target files changed
