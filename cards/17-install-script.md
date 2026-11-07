# Card: Install / update script

**Target files:** deploy/install.sh, README.md, ARCHITECTURE.md
**Goal:** One idempotent command that installs or updates Gameday Lights as a systemd --user service on Linux.

## Contract
- `deploy/install.sh [--pull] [--skip-tests] [--no-restart] [--dry-run]`; safe to rerun
- Steps: preflight (Linux, systemd user manager, uv) -> optional `git pull --ff-only` -> `uv sync --frozen` -> create `config.toml` from the example if missing (then stop) -> validate config -> tests -> render the unit with this checkout's real path -> install if changed -> enable -> start or restart -> linger hint -> status
- Never runs a command that touches the bulb; never installs uv for the user; stops on the first failure

## Done when
- [ ] `bash -n` passes and `--dry-run` prints every step without changing anything
- [ ] Only the target files changed
