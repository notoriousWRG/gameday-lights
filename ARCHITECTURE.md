# Architecture

One process, asyncio, SQLite for state. See `intent.md` for the why.

```
app/config.py            TOML -> dataclasses (teams, bulbs, effects, delays, intervals, dispatch_enabled)
app/store.py             SQLite: games, team_scores(score, increase_n), events(dedupe_key UNIQUE, detected_at, due_at, fired_at, status)
app/espn/client.py       the ONLY ESPN caller: httpx async, TTL cache, timeout, exp. backoff
app/espn/detect.py       pure: detect(prev, curr, followed_ids) -> list[ScoreChange]
app/espn/schedule.py     pure: parse team schedule -> Game rows
app/bulbs/base.py        BulbAdapter protocol (set_color, flash(pattern), snapshot, restore), Pattern + 2/s cap, DryRunBulb
app/bulbs/wiz.py         pywizlight adapter, MAC re-discovery
app/effects.py           effect config + team colors -> Pattern
app/dispatch/dispatcher.py  delay wait, per-bulb serial queue, snapshot/restore, dry-run, logs fired_at
app/watcher.py           schedule-sync loop + game-watcher loop, poll policy, baseline-on-start, event creation
app/main.py              wiring + CLI: run | run --replay DIR | discover | test-effect
scripts/                 Phase 0 probes
deploy/systemd/          user unit
```

Event shape: `{game, team, type, detail, detected_at}` plus `dedupe_key`, `due_at`, `fired_at`, `status`.

This file lists the planned tree; card C16 syncs it with what was actually built.
