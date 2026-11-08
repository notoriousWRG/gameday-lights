# Card: bulb `kind` in config and settings

**Target files:** app/config.py, app/settings.py, tests/test_config.py, tests/test_settings.py
**Goal:** Each bulb has a `kind` (`"wiz"` default, or `"govee"`), stored and validated like the other bulb fields, so existing configs and stored settings keep working.

## Contract
- `BulbConfig.kind: str = "wiz"`; allowed kinds `("wiz", "govee")`; unknown kind is a `ConfigError` naming the field
- `port` defaults by kind when omitted: wiz 38899, govee 4003
- `kind` is accepted in `_BULB_KEYS`, round-trips through `sections_from_config` and the TOML export/import, and is not secret
- A bulb with no `kind` in old stored settings loads as `"wiz"`

## Constraints
- Do not change how any other field validates. Do not touch main.py or the web files.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A TOML bulb with `kind = "govee"` and no port parses with port 4003
- [ ] Only the target files changed
