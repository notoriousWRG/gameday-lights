# Game Lights

A small home server that watches your teams' games through ESPN's unofficial API and pulses a smart bulb in team colors when they score, delayed to land with a streamed TV picture.

Status: Phase 1 (headless server, WiZ bulbs, NFL first). See `intent.md` for the vision, `PLAN.md` for progress, `DECISIONS.md` for settled choices and `ARCHITECTURE.md` for the code map.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) and run `uv sync`.
2. In the WiZ app, join the bulb to your 2.4 GHz Wi-Fi. Under Security, turn **off** "only allow verified controls" (otherwise the bulb rejects local commands with `Invalid params`).
3. `cp config.example.toml config.toml` and edit it: bulb IP and MAC (`uv run game-lights discover` prints them), the teams you follow, colors, delay. `config.toml` is gitignored.
4. Try the bulb: `uv run game-lights test-effect score --team GB`

Exactly one instance should drive a given bulb: set `dispatch_enabled = false` on any other machine (it then only logs what it would do).

## Run

```bash
uv run game-lights run                 # live; add --dry-run to log effects without touching the bulb
uv run game-lights run --replay tests/fixtures/nfl/<event_id> --fresh   # replay a recorded game, dry-run, 60x speed
uv run game-lights discover            # find WiZ bulbs on the LAN
```

Replays keep their own database (`<db>.replay.db`), so they never mix with live state. Kill and rerun without `--fresh` to confirm nothing fires twice.

### As a service (systemd --user)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/game-lights.service ~/.config/systemd/user/   # edit the paths if needed
systemctl --user daemon-reload
systemctl --user enable --now game-lights
loginctl enable-linger $USER           # keep running when logged out
journalctl --user -u game-lights -f    # logs
```

Each score is stored in the `events` table of the SQLite database with its detected, due and fired times and a status (`fired`, `dry_run`, `failed`, `skipped_restart`).

## Development

```bash
uv run pytest
uv run ruff check
```

Phase 0 probes live in `scripts/` (`probe_scoreboard.py`, `probe_bulb.py`).

## License

MIT
