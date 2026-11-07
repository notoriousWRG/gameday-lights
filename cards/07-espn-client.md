# Card: ESPN client

**Target files:** app/espn/client.py, tests/test_espn_client.py (the only files to edit)
**Goal:** The only module that calls ESPN: async httpx, per-endpoint TTL cache, timeout, exponential backoff.

## Context to read (read-only)
- intent.md: "The data source" endpoint table
- CLAUDE.md: never poll faster than every 10 s; every ESPN call goes through this file

## Contract
- `EspnClient(transport=None, clock=time.monotonic, sleep=asyncio.sleep, timeout_s=10, retries=3, backoff_s=1.0)`
- `await scoreboard(league, date=None)`, `team_schedule(league, team_id, seasontype=None)`, `teams(league)`, `aclose()`
- `league` is `"nfl"`, `"nhl"` or an explicit `"sport/league"` path; anything else raises `EspnError`
- TTLs: scoreboard 10 s (a floor, never lower), schedule 1 h, teams 24 h
- Retry on transport errors, 429 and 5xx with delays `backoff_s * 2**attempt`; other 4xx fail at once; `EspnError` after the last attempt

## Constraints
- Tests use `httpx.MockTransport` and fake clock/sleep; no network.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Two scoreboard calls inside 10 s make one HTTP request
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error.
