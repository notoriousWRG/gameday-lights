# Card: Heartbeat ping

**Target files:** app/health.py (new), app/config.py, app/settings.py, config.example.toml, app/main.py (start the task), tests/test_health.py (new)
**Goal:** If `[health] heartbeat_url` is set, ping it every `heartbeat_interval_s` (default 300, never below 60). Unset means no call at all. Missing network never crashes the server.

## Constraints
- It is one of the three allowed outbound calls (ESPN, heartbeat, notifier). Use httpx with a short timeout; log failures once per outage, not every try.
- Interval is config, not hard-coded. Tests use a fake transport, never the network.

## Done when
- [ ] pytest and ruff pass; unset URL makes zero requests (tested)
