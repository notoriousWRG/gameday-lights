# Card: "Update available" note (opt-in)

**Target files:** app/releases.py (new), app/config.py, app/settings.py, config.example.toml, app/web/routes_diagnostics.py, tests/test_releases.py (new)
**Goal:** Off by default. With `[updates] check = true` the server asks the GitHub Releases API for the latest tag once a day (never during a live game) and Diagnostics shows "vX.Y.Z available; run the updater". It never installs anything.

## Constraints
- New outbound call: add it to the allowed list in CLAUDE.md and DECISIONS.md in the same change (user approved a public repo and this check on 2026-11-15, pending final yes when the card runs).
- Cache the answer; ignore failures silently; fixture-based tests.

## Done when
- [ ] pytest and ruff pass; disabled means zero requests (tested)
