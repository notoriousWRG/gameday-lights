"""game-lights CLI: run | run --replay DIR | discover | test-effect."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from collections.abc import Coroutine
from datetime import datetime, timedelta

from app.bulbs.base import BulbAdapter, DryRunBulb
from app.bulbs.wiz import WizBulb
from app.config import Config, ConfigError, TeamConfig, load_config
from app.dispatch.dispatcher import Dispatcher, make_planner, resolve_pattern, utc_now
from app.espn.client import EspnClient, EspnError
from app.espn.replay import ReplayClient
from app.espn.schedule import parse_team_colors
from app.store import Store
from app.watcher import Watcher

log = logging.getLogger("game-lights")


class VirtualClock:
    """Time that runs `speed` times faster than the wall clock, for replays."""

    def __init__(self, start: datetime, speed: float) -> None:
        self._start, self._speed, self._t0 = start, speed, time.monotonic()

    def now(self) -> datetime:
        return self._start + timedelta(seconds=(time.monotonic() - self._t0) * self._speed)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self._speed)


def make_bulbs(cfg: Config, dry: bool, sleep=asyncio.sleep) -> dict[str, BulbAdapter]:
    if dry:
        return {b.name: DryRunBulb(b.name, sleep=sleep) for b in cfg.bulbs}
    return {
        b.name: WizBulb(b.name, b.ip, mac=b.mac, port=b.port, signing_key=b.signing_key,
                        sleep=sleep)
        for b in cfg.bulbs
    }


async def fetch_team_colors(cfg: Config, client) -> dict:
    colors = {}
    for t in cfg.teams:
        try:
            colors[(t.league, t.id)] = parse_team_colors(await client.team(t.league, t.id))
        except (EspnError, ValueError) as e:
            log.warning("no ESPN colors for %s/%s (%s); config colors or defaults apply",
                        t.league, t.abbr, e)
    return colors


def run_until_signal(coro: Coroutine) -> None:
    async def wrapper() -> None:
        task = asyncio.ensure_future(coro)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, task.cancel)
            except NotImplementedError:  # Windows
                pass
        try:
            await task
        except asyncio.CancelledError:
            log.info("stopping")

    asyncio.run(wrapper())


async def run_live(cfg: Config, dry_run: bool) -> None:
    dry = dry_run or not cfg.general.dispatch_enabled
    log.info("starting: %d team(s), %d bulb(s), %s", len(cfg.teams), len(cfg.bulbs),
             "DRY-RUN (no bulb commands)" if dry else "dispatch ENABLED")
    client = EspnClient()
    store = Store(cfg.general.db_path)
    dispatcher = None
    try:
        colors = await fetch_team_colors(cfg, client)
        dispatcher = Dispatcher(store, make_bulbs(cfg, dry), make_planner(cfg, colors, store),
                                dry_run=dry)
        dispatcher.recover()
        await Watcher(cfg, store, client, dispatcher, utc_now).run()
    finally:
        if dispatcher:
            await dispatcher.aclose()
        await client.aclose()
        store.close()


async def run_replay(cfg: Config, directory: str, speed: float, fresh: bool) -> None:
    db = cfg.general.db_path.with_suffix(".replay.db")
    if fresh:
        db.unlink(missing_ok=True)
    client = ReplayClient(directory)
    clock = VirtualClock(client.start_time - timedelta(minutes=5), speed)
    store = Store(db)
    dispatcher = Dispatcher(store, make_bulbs(cfg, True, clock.sleep), make_planner(cfg, {}, store),
                            clock.now, clock.sleep, dry_run=True)
    window = timedelta(minutes=cfg.general.watch_lead_min)
    try:
        dispatcher.recover()
        watcher = Watcher(cfg, store, client, dispatcher, clock.now, clock.sleep)
        await watcher.sync_schedule()
        while not client.finished:
            interval = await watcher.poll_once()
            if not store.upcoming_games(clock.now(), window):
                break  # game is final
            await clock.sleep(interval)
        await dispatcher.wait_idle()
        print(f"\nReplay done ({db.name}). Events:")
        rows = store.db.execute("SELECT * FROM events ORDER BY id").fetchall()
        for r in rows:
            fired = r["fired_at"]
            gap = (
                f"fired {(datetime.fromisoformat(fired) - datetime.fromisoformat(r['detected_at'])).total_seconds():.0f}s after detection"  # noqa: E501
                if fired else "never fired"
            )
            print(f"  {r['dedupe_key']:<14} {r['status']:<16} {r['detail']}  {gap}")
        if not rows:
            print("  (none)")
    finally:
        await dispatcher.aclose()
        store.close()


async def discover(broadcast: str) -> None:
    from pywizlight.discovery import discover_lights

    bulbs = await discover_lights(broadcast_space=broadcast, wait_time=5)
    if not bulbs:
        print("No WiZ bulbs found.")
    for b in bulbs:
        print(f"{b.ip}  mac {b.mac}")


async def test_effect(cfg: Config, abbr: str, dry_run: bool) -> int:
    team = next((t for t in cfg.teams if t.abbr.lower() == abbr.lower()), None)
    if team is None:
        print(f"Team {abbr!r} is not in the config.", file=sys.stderr)
        return 2
    colors = ((0, 255, 0), (255, 255, 255))
    if not (team.color and team.alt_color):
        client = EspnClient()
        try:
            colors = (await fetch_team_colors(cfg, client)).get((team.league, team.id), colors)
        finally:
            await client.aclose()
    pattern = resolve_pattern(cfg, team, *colors)
    dry = dry_run or not cfg.general.dispatch_enabled
    bulbs = make_bulbs(cfg, dry, _instant if dry else asyncio.sleep)
    print(f"{team.abbr}: {len(pattern.steps)} steps over {pattern.duration_s:.1f}s on "
          f"{', '.join(team.bulbs)}{' (dry-run)' if dry else ''}")
    await _play(bulbs, team, pattern)
    print("Done.")
    return 0


async def _instant(seconds: float) -> None:
    await asyncio.sleep(0)


async def _play(bulbs: dict[str, BulbAdapter], team: TeamConfig, pattern) -> None:
    async def one(b: BulbAdapter) -> None:
        snap = await b.snapshot()
        try:
            await b.flash(pattern)
        finally:
            await b.restore(snap)

    await asyncio.gather(*(one(bulbs[n]) for n in team.bulbs))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="game-lights", description=__doc__)
    p.add_argument("--config", default="config.toml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="watch games and fire effects")
    run.add_argument("--replay", metavar="DIR", help="replay recorded scoreboard fixtures")
    run.add_argument("--speed", type=float, default=60.0, help="replay speed multiplier")
    run.add_argument("--fresh", action="store_true", help="replay: start with an empty database")
    run.add_argument("--dry-run", action="store_true", help="log effects, don't touch bulbs")
    d = sub.add_parser("discover", help="find WiZ bulbs on the LAN")
    d.add_argument("--broadcast", default="255.255.255.255")
    t = sub.add_parser("test-effect", help="play an effect on a team's bulbs")
    t.add_argument("effect", choices=["score"])
    t.add_argument("--team", required=True)
    t.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        if args.command == "discover":
            asyncio.run(discover(args.broadcast))
            return 0
        cfg = load_config(args.config)
        if args.command == "run":
            if args.replay:
                if args.speed <= 0:
                    print("--speed must be positive", file=sys.stderr)
                    return 2
                asyncio.run(run_replay(cfg, args.replay, args.speed, args.fresh))
            else:
                run_until_signal(run_live(cfg, args.dry_run))
            return 0
        return asyncio.run(test_effect(cfg, args.team, args.dry_run))
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
