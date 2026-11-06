"""Phase 0 probe: watch one team's game on the ESPN scoreboard.

Logs score changes to CSV, saves changed responses as gzipped fixtures, and
pairs Enter keypresses (press when the score shows on TV) with the latest
unpaired detected change to measure ESPN-to-TV lag.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import statistics
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

SPORTS = {"nfl": "football/nfl", "nhl": "hockey/nhl"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/{sport}/scoreboard"
MIN_INTERVAL = 10.0
IDLE_INTERVAL = 60.0
BREAK_STATUSES = {"STATUS_HALFTIME", "STATUS_END_PERIOD", "STATUS_DELAYED"}
FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


@dataclass
class Change:
    detected_at: datetime
    team: str
    old: int
    new: int
    pressed_at: datetime | None = None

    @property
    def delta(self) -> int:
        return self.new - self.old

    @property
    def lag_s(self) -> float | None:
        if self.pressed_at is None:
            return None
        return (self.pressed_at - self.detected_at).total_seconds()


def find_game(scoreboard: dict, abbr: str) -> dict | None:
    for event in scoreboard.get("events", []):
        for comp in event.get("competitions", [])[:1]:
            for c in comp.get("competitors", []):
                if c.get("team", {}).get("abbreviation", "").upper() == abbr.upper():
                    return event
    return None


def scores(event: dict) -> dict[str, int]:
    """Map team abbreviation -> score for an event."""
    out: dict[str, int] = {}
    for c in event["competitions"][0]["competitors"]:
        out[c["team"]["abbreviation"]] = int(c.get("score") or 0)
    return out


def status_of(event: dict) -> tuple[str, str]:
    t = event.get("status", {}).get("type", {})
    return t.get("state", ""), t.get("name", "")


def content_hash(data: dict) -> str:
    blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def diff_scores(prev: dict[str, int] | None, curr: dict[str, int]) -> list[tuple[str, int, int]]:
    if prev is None:
        return []
    return [(t, prev.get(t, 0), s) for t, s in curr.items() if s != prev.get(t, 0)]


def pair_press(changes: list[Change], press_ts: datetime) -> Change | None:
    """Pair a keypress with the latest unpaired change detected before it."""
    for ch in reversed(changes):
        if ch.pressed_at is None and ch.detected_at <= press_ts:
            ch.pressed_at = press_ts
            return ch
    return None


def lag_summary(changes: list[Change]) -> str:
    lags = [c.lag_s for c in changes if c.lag_s is not None]
    if not lags:
        return "No paired lag measurements."
    parts = [
        f"{len(lags)} paired of {len(changes)} changes",
        f"mean {statistics.mean(lags):.1f}s",
        f"min {min(lags):.1f}s",
        f"max {max(lags):.1f}s",
    ]
    if len(lags) > 1:
        parts.append(f"stdev {statistics.stdev(lags):.1f}s")
    return "Lag (detected -> pressed): " + ", ".join(parts)


def save_fixture(data: dict, league: str, event_id: str, seq: int, now: datetime) -> Path:
    d = FIXTURE_ROOT / league / event_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{seq:04d}_{now.strftime('%Y%m%dT%H%M%S')}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def write_csv(path: Path, changes: list[Change]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["detected_at", "team", "old", "new", "delta", "pressed_at", "lag_s"])
        for c in changes:
            w.writerow([
                c.detected_at.isoformat(), c.team, c.old, c.new, c.delta,
                c.pressed_at.isoformat() if c.pressed_at else "",
                f"{c.lag_s:.1f}" if c.lag_s is not None else "",
            ])


def start_enter_listener(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    def run() -> None:
        for _ in sys.stdin:
            loop.call_soon_threadsafe(queue.put_nowait, datetime.now(UTC))

    threading.Thread(target=run, daemon=True).start()


async def fetch(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    r = await client.get(url, params=params, timeout=10.0)
    r.raise_for_status()
    return r.json()


async def probe(args: argparse.Namespace) -> None:
    url = BASE.format(sport=SPORTS[args.league])
    params = {"dates": args.date} if args.date else {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    changes: list[Change] = []
    presses: asyncio.Queue = asyncio.Queue()
    start_enter_listener(asyncio.get_running_loop(), presses)

    prev: dict[str, int] | None = None
    last_hash = ""
    seq = 0
    csv_path: Path | None = None
    backoff = 0

    async with httpx.AsyncClient() as client:
        try:
            while True:
                interval = args.interval
                try:
                    board = await fetch(client, url, params)
                    backoff = 0
                except httpx.HTTPError as e:
                    backoff = min(backoff + 1, 5)
                    print(f"fetch failed ({e}); backing off", file=sys.stderr)
                    await asyncio.sleep(args.interval * 2**backoff)
                    continue
                now = datetime.now(UTC)
                event = find_game(board, args.team)
                if event is None:
                    print(f"No {args.team} game on the {args.league} scoreboard for this date.")
                    return
                event_id = event["id"]
                state, name = status_of(event)
                curr = scores(event)
                csv_path = csv_path or out / f"{args.league}_{event_id}_changes.csv"

                if state != "pre":
                    # Fixture of the whole response, only when content changed.
                    h = content_hash(board)
                    if h != last_hash:
                        seq += 1
                        save_fixture(board, args.league, event_id, seq, now)
                        last_hash = h
                    for team, old, new in diff_scores(prev, curr):
                        changes.append(Change(now, team, old, new))
                        print(f"{now:%H:%M:%S} {team} {old}->{new}  (press Enter when TV shows it)")
                    if prev is None:
                        print(f"Baseline: {curr} ({name})")
                    prev = curr
                else:
                    interval = IDLE_INTERVAL
                    print(f"{now:%H:%M:%S} pre-game; waiting ({event.get('shortName', '')})")

                while not presses.empty():
                    ch = pair_press(changes, presses.get_nowait())
                    print(f"  paired: lag {ch.lag_s:.1f}s" if ch else "  keypress: nothing to pair")
                write_csv(csv_path, changes)

                if state == "post":
                    print("Game final.")
                    return
                if name in BREAK_STATUSES:
                    interval = IDLE_INTERVAL
                await asyncio.sleep(interval)
        finally:
            if csv_path:
                write_csv(csv_path, changes)
                print(f"\nCSV: {csv_path}")
            print(lag_summary(changes))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--team", required=True, help="team abbreviation, e.g. GB")
    p.add_argument("--league", default="nfl", choices=sorted(SPORTS))
    p.add_argument("--interval", type=float, default=15.0, help="live poll seconds (>= 10)")
    p.add_argument("--date", help="YYYYMMDD; default is ESPN's current scoreboard")
    p.add_argument("--out", default="probe_out", help="directory for the CSV")
    args = p.parse_args()
    if args.interval < MIN_INTERVAL:
        p.error(f"--interval must be >= {MIN_INTERVAL:g} seconds")
    try:
        asyncio.run(probe(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
