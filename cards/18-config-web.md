# Card: [web] config section

**Target files:** app/config.py, config.example.toml, tests/test_config.py
**Goal:** `[web]` table for the status page: `enabled`, `host`, `port`.
**Contract:** `WebConfig(enabled=True, host="127.0.0.1", port=8787)` as `Config.web` (default when the table is absent); port 1-65535, host non-empty; `ConfigError` names the field.
**Constraints:** default host is loopback. LAN access is an explicit choice (set a LAN address); nothing public.
**Done when:** `uv run pytest` and `uv run ruff check` pass; only the target files changed.
