# Gameday Lights

A small home server that watches your teams' games through ESPN's unofficial API and pulses a smart bulb in team colors when they score, delayed to land with a streamed TV picture.

Status: Phase 1 (headless server, WiZ bulbs, NFL first). See `intent.md` for the vision, `PLAN.md` for progress, `DECISIONS.md` for settled choices and `ARCHITECTURE.md` for the code map.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) and run `uv sync`.
2. In the WiZ app, join the bulb to your 2.4 GHz Wi-Fi. Under Security, turn **off** "only allow verified controls" (otherwise the bulb rejects local commands with `Invalid params`).
3. `cp config.example.toml config.toml` and edit it: bulb IP and MAC (`uv run gameday-lights discover` prints them), the teams you follow, colors, delay. `config.toml` is gitignored.
4. Try the bulb: `uv run gameday-lights test-effect score --team GB`

Exactly one instance should drive a given bulb: set `dispatch_enabled = false` on any other machine (it then only logs what it would do).

## Run

```bash
uv run gameday-lights run                 # live; add --dry-run to log effects without touching the bulb
uv run gameday-lights run --replay tests/fixtures/nfl/<event_id> --fresh   # replay a recorded game, dry-run, 60x speed
uv run gameday-lights discover            # find WiZ bulbs on the LAN
```

Replays keep their own database (`<db>.replay.db`), so they never mix with live state. Kill and rerun without `--fresh` to confirm nothing fires twice.

### As a service (systemd --user)

One script installs or updates it, and is safe to rerun:

```bash
deploy/install.sh              # first install, or after editing config.toml
deploy/install.sh --pull       # update to the latest commit, then restart
```

It checks uv and systemd, syncs dependencies from the lockfile, creates `config.toml` from the example if missing (and stops so you can edit it), validates the config, runs the tests, installs the unit with this checkout's real path, then starts or restarts the service. Other options: `--skip-tests`, `--no-restart` (leave a running service alone; use this mid-game), `--dry-run` (print the steps, change nothing).

```bash
journalctl --user -u gameday-lights -f    # logs
loginctl enable-linger $USER              # keep running when logged out (the script tells you if it's off)
```

Each score is stored in the `events` table of the SQLite database with its detected, due and fired times and a status (`fired`, `dry_run`, `failed`, `skipped_restart`).

## Status page

While `run` is going, a page shows what the server is doing. At the top, a **Scoreboard** card shows the game in progress (score, quarter-by-quarter, clock, down and distance when ESPN provides it, broadcast, and that the server is polling and how often); a finished game stays up for `final_hold_min` after the final whistle; otherwise it shows a card for the next game of each team you follow (up to three, soonest first: "Tonight", "Tomorrow", "This week" or "Next game", with a live countdown); while a game is on, the other teams' next games appear as "Next up" lines under it. Below that: watcher health, bulb reachability, the whole schedule (final scores with W/L for finished games, the running score for a live game, day and time for upcoming ones; with two or more followed teams each row is tagged with its team, and buttons filter to one team, with each team's next game highlighted) and recent events with how long after detection each effect fired. The **Pulse** button next to each bulb runs the same check as `test-effect` (the bulb flashes its team colors for about 6 seconds, then restores); it waits behind a real effect if one is playing and has a short cooldown, and in dry-run mode it sends nothing to the bulb. Open <http://127.0.0.1:8787/> (JSON at `/api/status`). To see it from a phone or TV, set `host` under `[web]` in `config.toml` to this machine's LAN address. It has no login, so keep it on your home network. Set `enabled = false` to turn it off.

## Settings

Two kinds of settings:

- **Machine settings stay in `config.toml`**: `db_path`, `dispatch_enabled` and the `[web]` address. `dispatch_enabled` is deliberately not editable from the app: it is what stops a dev machine from driving your bulb.
- **Everything else is stored in the database**: followed teams, bulbs (including signing keys), effects, `delay_s`, and the timings (poll, sync, watch lead, pulse cooldown, final hold). The first start imports them from `config.toml`; after that the stored settings win, and a differing file is only reported in the log.

Stored settings change while the server runs, with no restart. Edits go through `PUT /api/settings/{section}` (sections: `bulbs`, `teams`, `effects`, `household`, `advanced`; `GET /api/settings` lists them with revisions). A write needs an `X-Gameday: 1` header and `If-Match: <revision>`: a stale revision gets 409 (so two phones cannot overwrite each other) and an invalid value gets 422 with the field. The same rules apply as for `config.toml` (poll never below 10 s, flash cap, teams must use an existing bulb). Bulb signing keys can be set but are never returned. 
The **Teams** tab (next to Status) is the first editing screen: it lists the teams you follow with their bulbs and colors, lets you search ESPN's NFL and NHL team lists and follow a team (colors pre-filled from ESPN, with a warning when a color is too dark to show on a bulb), and saves through the API above. Changes are a draft until you press Save; a stale list is refused rather than overwritten. A new team's schedule loads within seconds, without a restart. Bulbs, effects, delay and the timings do not have screens yet.

```bash
uv run gameday-lights config export                 # the stored settings as config.toml text (--no-secrets leaves out signing keys)
uv run gameday-lights config import --force         # replace the stored settings with config.toml's values
```

## Development

```bash
uv run pytest
uv run ruff check
```

Phase 0 probes live in `scripts/` (`probe_scoreboard.py`, `probe_bulb.py`).

## License

MIT
