# Gameday Lights: rules for Claude

Read `intent.md` (vision), `PLAN.md` (card queue), `DECISIONS.md` (settled choices) before working.

## Commands
- Tests: `uv run pytest`
- Lint: `uv run ruff check`
- Run: `uv run gameday-lights run`

## Rules
- Every ESPN call goes through `app/espn/client.py`; never call ESPN from anywhere else.
- Tests never hit the network; use recorded fixtures under `tests/fixtures/`.
- Bulbs are only touched through the adapter interface (`app/bulbs/base.py`); always snapshot and restore state.
- Polling intervals, delays, colors and quiet hours are config values, never hard-coded.
- Never poll faster than every 10 seconds; poll only during live windows.
- Flash rate is capped in code at 2 color changes/sec; config cannot exceed it.
- Nothing binds outside the LAN; no cloud bulb APIs. Outbound calls: ESPN, the heartbeat URL, the configured notifier.
- Bulbs must be addable by static IP as well as discovered.
- Nothing assumes a specific team, league, brand, host OS or household; all of it is configuration.
- Portable code: `pathlib` for paths, no systemd/fork-only assumptions in app code, all times stored in UTC.
- Never commit secrets: `config.toml` is gitignored, `config.example.toml` is committed.
- Do not `git init` or commit; the user owns git.

## Card workflow
One card per module (module + its test file). Work from `cards/NN-<slug>.md`, edit only its target files, run the check commands. If a check fails, fix once with the error output; a second failure means stop and report what was tried and the exact error. Stop for review after each card group.
