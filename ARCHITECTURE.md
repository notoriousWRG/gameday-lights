# Architecture

One process, asyncio, SQLite for state. See `intent.md` for the why and `DECISIONS.md` for settled choices.

```
app/main.py              CLI + wiring: run | run --replay DIR | discover | test-effect
app/config.py            TOML -> frozen dataclasses; validates poll >= 10 s, bulb refs, flash cap
app/settings.py          which settings are stored vs machine-only; Config <-> stored sections; error_location
app/settings_service.py  seed from config.toml, current snapshot, validated edits with revisions, export
app/store.py             SQLite (schema v3 via PRAGMA user_version; created 0600): games (with home/away and scores), settings + settings_history, team_scores(score, increase_n),
                         events(dedupe_key UNIQUE, detected_at, due_at, fired_at, status)
app/watcher.py           schedule-sync + game-watch loops, poll policy, restart baseline, event creation
app/effects.py           EffectConfig + parse_color + build_pattern (slow pulse)
app/espn/client.py       the ONLY ESPN caller: httpx, TTL cache (scoreboard floor 10 s), backoff
app/espn/detect.py       pure: team_scores, detect(prev, curr, followed_ids), score_label
app/espn/schedule.py     pure: parse_schedule, merge_schedules, parse_team_colors, parse_scoreboard_game
app/espn/replay.py       offline stand-in for EspnClient that replays recorded fixtures
app/web/status.py        status page (FastAPI + uvicorn): GET /, GET /api/status, POST /api/bulbs/{name}/pulse; LAN only
app/web/status.html      the page: vanilla JS, textContent only, refreshes every 10 s
app/bulbs/base.py        BulbAdapter ABC, Pattern/Step with the 2 changes/sec cap, DryRunBulb
app/bulbs/wiz.py         pywizlight adapter, snapshot/restore, MAC re-discovery
app/dispatch/dispatcher.py  delay wait, per-bulb serial queue, snapshot/restore, make_planner/resolve_pattern
scripts/probe_scoreboard.py  Phase 0: log score changes, record fixtures, measure TV lag (Enter key)
scripts/probe_bulb.py        Phase 0: discover, RTT, pulse, optional burst test
deploy/systemd/gameday-lights.service   user unit template (%h/hack/gameday-lights is rewritten to the real path)
deploy/install.sh        idempotent install/update for Linux + systemd --user
cards/                   task cards (one per module)
tests/                   pytest; fixtures under tests/fixtures/ (recorded ESPN JSON)
```

## Flow

1. `Watcher.sync_schedule` (every `schedule_sync_hours`) upserts each followed team's games with teams and scores; a game's status never moves backwards, and a cached schedule never overwrites a score a live poll recorded.
2. `Watcher.poll_once` makes HTTP calls only for games inside their window (from `watch_lead_min` before kickoff until final). It sleeps `poll_live_s` while live, `poll_break_s` at breaks, before kickoff and when idle.
3. The first sight of a team in a process is a baseline through the store; increases missed while down become `skipped_restart` events. Later increases bump `increase_n` and insert a `pending` event with key `game:team:n` and `due_at = detected_at + delay_s`.
4. `Dispatcher` sleeps until `due_at`, then plays the pattern on the team's bulbs: one effect at a time per bulb, always snapshot and restore. Statuses: `fired`, `dry_run`, `failed`, `skipped_restart`.

## Settings and live apply

`config.toml` holds the machine settings; teams, bulbs, effects, delay and timings are stored sections (`settings` table: JSON plus a revision; `settings_history` keeps secrets-free copies). `config.parse_config` is the single validation path for the file and for UI edits. `SettingsService.update` validates the whole new config before writing, checks the revision (409 if stale), swaps the snapshot and calls subscribers. The watcher, planner, dispatcher and page take a config provider and read it at use time; `main.make_live_apply` is the subscriber that requests a schedule sync when followed teams change, swaps the bulb registry (an unchanged bulb keeps its adapter and queue) and refreshes ESPN colors. A team that is followed mid-game is baselined on its first poll and fires from its next score.

## Teams screen

The page has a nav (Status, Teams; hash routes). The Teams screen works on a draft of the `teams` section and saves it with `PUT /api/settings/teams` (`If-Match`, `X-Gameday`): 422 messages are shown under the team row they belong to and clear when that team is edited; 409 offers "Load latest". `GET /api/leagues` and `GET /api/teams/search` (ESPN's cached team list with colors, `followed` marked per league) feed the search. The page file is read once when the server starts, so the page always matches the running API.

## Status page

`run` also serves a status page (`[web]` in config; default `127.0.0.1:8787`, set `host` to a LAN address to view it from a phone; it has no login, so never expose it to the internet). The only write action is the per-bulb **Pulse** button (`POST /api/bulbs/{name}/pulse`): it plays the bulb's team pattern through the dispatcher (same per-bulb queue and snapshot/restore as real events, so it never overlaps one; not recorded as an event). It requires an `X-Gameday: 1` header (a cross-site form post cannot send it without a CORS preflight, which is never granted) and has a per-bulb cooldown (`[web].pulse_cooldown_s`). The top Scoreboard card shows games in their window (live or pre-game, with a polling indicator), a just-finished game for `[web].final_hold_min`, or else one card per followed team's next game (up to `MAX_NEXT_GAMES` = 3, soonest first, a game two followed teams share shown once) with a countdown; its data is `Watcher.stats.live`, which the watcher refreshes from every scoreboard poll (in memory only). It also shows mode, watcher health (last poll, errors), bulb reachability (`ping`, cached 30 s), one Schedule card with every game (final score and W/L, live score, or day and time), one row per followed team in each game and a per-team filter (teams are identified by league + abbreviation, since PIT is both the Steelers and the Penguins), and the last 25 events with detected -> fired timing. Handlers are async because the sqlite connection lives on the event loop thread. uvicorn runs without its own signal handlers; `main.run_tasks` cancels and then waits for each task so shutdown stays clean.

## Deviations from the original plan

- `detect.py` (C04) was written before the recorded GB @ NE game and still needs re-checking against it.
- `replay.py` and `resolve_pattern` were added to support offline replay and `test-effect`.
- Team colors from ESPN are fallbacks; config colors override them.
