# Card: Version and diagnostics API

**Target files:** app/web/routes_diagnostics.py (new), app/web/status.py (mount only), app/main.py (`--version`), tests/test_web_diagnostics.py (new)
**Goal:** `GET /api/diagnostics` returns what a friend would text me: version (from package metadata), Python and OS, data dir, uptime, last ESPN poll and result, last event, per-bulb reachability, followed teams, practice/dry-run flags. `gameday-lights --version` prints the version.

## Context to read (read-only)
- app/web/common.py, app/web/data.py: how routes read watcher and bulb state
- DECISIONS.md: signing keys are write-only, never returned

## Contract
- Response is JSON, read-only, no secrets (no signing keys, SMTP password, heartbeat or webhook URLs; show only whether each is set)
- `bundle` field: a plain-text version of the same facts, ready to paste into a text message

## Constraints
- No new outbound calls. Times in UTC.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] A test proves no secret value appears anywhere in the response
- [ ] Only the target files changed
