# Card: Config loader

**Target files:** app/config.py, config.example.toml, tests/test_config.py (the only files to edit)
**Goal:** Parse a TOML file with stdlib `tomllib` into frozen dataclasses, validating everything that has a rule.

## Context to read (read-only)
- CLAUDE.md: rules (poll >= 10 s, config values not hard-coded)
- DECISIONS.md: Delay, Default effect, Bulb IP, Phase 1 run rows
- app/effects.py: `EffectConfig`, `parse_color`, `build_pattern`

## Contract
- `load_config(path) -> Config`; `ConfigError(ValueError)` for every problem, message names the field
- `Config(general, bulbs, teams, score_effect)`; `GeneralConfig(dispatch_enabled, db_path, delay_s=45, schedule_sync_hours=6, watch_lead_min=10, poll_live_s=15, poll_break_s=60)`
- `BulbConfig(name, ip, mac=None, port=38899, signing_key=None)`; `TeamConfig(league, id, abbr, bulbs, color=None, alt_color=None)`
- Rules: `poll_live_s` and `poll_break_s` >= 10; `delay_s` >= 0; team bulb names must exist; bulb and team keys unique; the score effect must build a valid Pattern (flash cap)
- Relative `db_path` resolves against the config file's directory

## Constraints
- Do not commit secrets: `config.example.toml` has placeholders only.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] `config.example.toml` loads with `load_config`
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
