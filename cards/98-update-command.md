# Card: `gameday-lights update`

**Target files:** app/update.py (new), app/main.py, tests/test_update.py (new)
**Goal:** `gameday-lights update [--to vX.Y.Z]` upgrades the installed tool via uv (`uv tool install --upgrade` from the release wheel), refuses while a game is live (`--force` overrides), backs up the database next to itself first (`.bak-<utc date>`, keep the last 3), and prints that the service must be restarted (the bootstrap scripts do the restart). Schema migrations already run on start; a downgrade refuses if the db schema is newer.

## Constraints
- App code stays OS-agnostic: run uv through `subprocess` with an argument list. Tests inject the runner; nothing real runs.

## Done when
- [ ] pytest and ruff pass (live-game refusal, backup rotation, newer-schema refusal tested)
