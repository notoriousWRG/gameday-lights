# Architecture

One process, asyncio, SQLite for state. See `intent.md` for the why and `DECISIONS.md` for settled choices.

```
app/main.py              CLI + wiring: run | run --replay DIR | discover | test-effect
app/config.py            TOML -> frozen dataclasses; validates poll >= 10 s, bulb refs, flash cap
app/store.py             SQLite (schema via PRAGMA user_version): games, team_scores(score, increase_n),
                         events(dedupe_key UNIQUE, detected_at, due_at, fired_at, status)
app/watcher.py           schedule-sync + game-watch loops, poll policy, restart baseline, event creation
app/effects.py           EffectConfig + parse_color + build_pattern (slow pulse)
app/espn/client.py       the ONLY ESPN caller: httpx, TTL cache (scoreboard floor 10 s), backoff
app/espn/detect.py       pure: team_scores, detect(prev, curr, followed_ids), score_label
app/espn/schedule.py     pure: parse_schedule, merge_schedules, parse_team_colors
app/espn/replay.py       offline stand-in for EspnClient that replays recorded fixtures
app/bulbs/base.py        BulbAdapter ABC, Pattern/Step with the 2 changes/sec cap, DryRunBulb
app/bulbs/wiz.py         pywizlight adapter, snapshot/restore, MAC re-discovery
app/dispatch/dispatcher.py  delay wait, per-bulb serial queue, snapshot/restore, make_planner/resolve_pattern
scripts/probe_scoreboard.py  Phase 0: log score changes, record fixtures, measure TV lag (Enter key)
scripts/probe_bulb.py        Phase 0: discover, RTT, pulse, optional burst test
deploy/systemd/game-lights.service   user unit
cards/                   task cards (one per module)
tests/                   pytest; fixtures under tests/fixtures/ (recorded ESPN JSON)
```

## Flow

1. `Watcher.sync_schedule` (every `schedule_sync_hours`) upserts each followed team's games; a game's status never moves backwards.
2. `Watcher.poll_once` makes HTTP calls only for games inside their window (from `watch_lead_min` before kickoff until final). It sleeps `poll_live_s` while live, `poll_break_s` at breaks, before kickoff and when idle.
3. The first sight of a team in a process is a baseline through the store; increases missed while down become `skipped_restart` events. Later increases bump `increase_n` and insert a `pending` event with key `game:team:n` and `due_at = detected_at + delay_s`.
4. `Dispatcher` sleeps until `due_at`, then plays the pattern on the team's bulbs: one effect at a time per bulb, always snapshot and restore. Statuses: `fired`, `dry_run`, `failed`, `skipped_restart`.

## Deviations from the original plan

- `detect.py` (C04) was written before the recorded GB @ NE game and still needs re-checking against it.
- `replay.py` and `resolve_pattern` were added to support offline replay and `test-effect`.
- Team colors from ESPN are fallbacks; config colors override them.
