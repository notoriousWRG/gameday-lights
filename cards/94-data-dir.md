# Card: Per-OS data directory

**Target files:** app/paths.py (new), app/main.py, app/config.py, config.example.toml, tests/test_paths.py (new)
**Goal:** An installed copy has no checkout to live in. Resolve a data dir: `--data-dir`, then `GAMEDAY_HOME`, then the OS default (Linux `~/.local/share/gameday-lights`, macOS `~/Library/Application Support/gameday-lights`, Windows `%LOCALAPPDATA%\gameday-lights`). `config.toml` and the database default to that dir; `--config` still overrides. A relative `db_path` still resolves against the settings file's folder (unchanged, so existing installs keep their database); installs keep the file in the data dir, so that is the data dir.

## Constraints
- `pathlib` only. Take the OS from `sys.platform`; no new dependency. Existing dev behaviour (`./config.toml` when it exists in cwd) must keep working.
- Tests pass the platform and env in as arguments so all three OS cases run on Linux.

## Done when
- [ ] pytest and ruff pass; all three OS defaults and each override are tested
