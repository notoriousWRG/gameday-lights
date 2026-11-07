"""gameday-lights CLI: run | run --replay DIR | discover | test-effect."""

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
from app.bulbs.wiz import WizBulb, discover_wiz
from app.config import (
    BulbConfig,
    Config,
    ConfigError,
    TeamConfig,
    load_config,
    load_raw,
    parse_config,
)
from app.dispatch.dispatcher import (
    Dispatcher,
    make_bulb_pulse,
    make_planner,
    make_team_pulse,
    resolve_pattern,
    utc_now,
)
from app.espn.client import EspnClient, EspnError
from app.espn.replay import ReplayClient
from app.espn.schedule import parse_team_colors
from app.settings import machine_raw_from_config
from app.settings_service import SettingsService
from app.store import Store
from app.watcher import Watcher
from app.web.status import create_app, serve_status

log = logging.getLogger("gameday-lights")


class VirtualClock:
    """Time that runs `speed` times faster than the wall clock, for replays."""

    def __init__(self, start: datetime, speed: float) -> None:
        self._start, self._speed, self._t0 = start, speed, time.monotonic()

    def now(self) -> datetime:
        return self._start + timedelta(seconds=(time.monotonic() - self._t0) * self._speed)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self._speed)


def make_bulb(b: BulbConfig, dry: bool, sleep=asyncio.sleep) -> BulbAdapter:
    if dry:
        return DryRunBulb(b.name, sleep=sleep)
    return WizBulb(b.name, b.ip, mac=b.mac, port=b.port, signing_key=b.signing_key, sleep=sleep)


def make_bulbs(cfg: Config, dry: bool, sleep=asyncio.sleep) -> dict[str, BulbAdapter]:
    return {b.name: make_bulb(b, dry, sleep) for b in cfg.bulbs}


def reconcile_bulbs(
    existing: dict[str, BulbAdapter], old: Config, new: Config, dry: bool, sleep=asyncio.sleep
) -> dict[str, BulbAdapter]:
    """The bulb registry for new settings: a bulb whose settings did not change keeps its adapter
    (and so its state and queue); changed and new bulbs get fresh ones; removed ones go."""
    before = {b.name: b for b in old.bulbs}
    return {
        b.name: existing[b.name]
        if b.name in existing and before.get(b.name) == b else make_bulb(b, dry, sleep)
        for b in new.bulbs
    }


def open_settings(config_path: str) -> tuple[SettingsService, Store]:
    """Open the database and the stored settings. The first start seeds them from config.toml;
    after that the stored settings win and a differing file is only reported."""
    raw, base_dir = load_raw(config_path)
    toml_cfg = parse_config(raw, base_dir)
    store = Store(toml_cfg.general.db_path)
    try:
        service = SettingsService(store, machine_raw_from_config(toml_cfg), base_dir)
        seeded = service.seed(toml_cfg)
        if seeded:
            log.info("imported %s from %s into the database", ", ".join(seeded), config_path)
        else:
            differing = service.diverged(toml_cfg)
            if differing:
                log.warning(
                    "%s differs from the stored settings for: %s. The stored settings are used; "
                    "run `gameday-lights config import --force` to take the file's values instead.",
                    config_path, ", ".join(differing))
        service.load()
    except BaseException:
        store.close()
        raise
    return service, store


async def fetch_team_colors(cfg: Config, client) -> dict:
    colors = {}
    for t in cfg.teams:
        try:
            colors[(t.league, t.id)] = parse_team_colors(await client.team(t.league, t.id))
        except (EspnError, ValueError) as e:
            log.warning("no ESPN colors for %s/%s (%s); config colors or defaults apply",
                        t.league, t.abbr, e)
    return colors


async def run_tasks(tasks: list[asyncio.Future]) -> None:
    """Run tasks together; on exit or cancel, cancel the rest and wait for their cleanup.

    Plain gather() re-raises the first cancellation immediately and abandons the other
    tasks mid-shutdown (e.g. the status server).
    """
    try:
        await asyncio.gather(*tasks)
    finally:
        for t in tasks:
            if not t.done() and t.cancelling() == 0:  # a second cancel would abort its cleanup
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


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


def make_live_apply(watcher, dispatcher, colors: dict, client, dry: bool, tasks: set):
    """The settings subscriber: pushes an edit into the running watcher and dispatcher."""

    async def refresh_colors(cfg: Config) -> None:
        colors.update(await fetch_team_colors(cfg, client))

    def apply(old: Config, new: Config) -> None:
        watcher.on_config_changed(old, new)
        if old.bulbs != new.bulbs:
            dispatcher.set_bulbs(reconcile_bulbs(dispatcher.bulbs, old, new, dry))
        if old.teams != new.teams:  # ESPN colors for a team that was just followed
            task = asyncio.ensure_future(refresh_colors(new))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    return apply


async def run_live(service: SettingsService, store: Store, dry_run: bool) -> None:
    cfg = service.config
    dry = dry_run or not cfg.general.dispatch_enabled
    log.info("starting: %d team(s), %d bulb(s), %s", len(cfg.teams), len(cfg.bulbs),
             "DRY-RUN (no bulb commands)" if dry else "dispatch ENABLED")
    client = EspnClient()
    dispatcher = None
    background: set[asyncio.Future] = set()
    current = lambda: service.config  # noqa: E731  (edits apply to the running server)
    try:
        colors = await fetch_team_colors(cfg, client)
        dispatcher = Dispatcher(store, make_bulbs(cfg, dry), make_planner(current, colors, store),
                                dry_run=dry)
        dispatcher.recover()
        watcher = Watcher(current, store, client, dispatcher, utc_now)
        service.subscribe(make_live_apply(watcher, dispatcher, colors, client, dry, background))
        tasks = [asyncio.ensure_future(watcher.run())]
        if cfg.web.enabled:
            app = create_app(store, current, watcher.stats, lambda: dispatcher.bulbs, dry,
                             dispatcher=dispatcher, pulse_pattern=make_bulb_pulse(current, colors),
                             settings=service, espn=client, discover_bulbs=discover_wiz,
                             team_pulse=make_team_pulse(current, colors))
            tasks.append(asyncio.ensure_future(serve_status(app, cfg.web.host, cfg.web.port)))
        await run_tasks(tasks)
    finally:
        for task in list(background):
            task.cancel()
        if dispatcher:
            await dispatcher.aclose()
        await client.aclose()


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


def config_command(args: argparse.Namespace, service: SettingsService) -> int:
    if args.config_command == "export":
        text = service.export_toml(include_secrets=not args.no_secrets)
        if "signing_key" in text:
            print("note: the export contains bulb signing keys; keep it private "
                  "(or use --no-secrets)", file=sys.stderr)
        print(text)
        return 0
    if not args.force:
        print("config import overwrites the stored settings with config.toml; "
              "pass --force to confirm", file=sys.stderr)
        return 2
    written = service.seed(load_config(args.config), force=True)
    print(f"imported: {', '.join(written)}" if written else "nothing to import: already identical")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gameday-lights", description=__doc__)
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
    c = sub.add_parser("config", help="export or re-import the stored settings")
    csub = c.add_subparsers(dest="config_command", required=True)
    ex = csub.add_parser("export", help="print the stored settings as config.toml text")
    ex.add_argument("--no-secrets", action="store_true", help="leave bulb signing keys out")
    im = csub.add_parser("import", help="replace stored settings with the values in config.toml")
    im.add_argument("--force", action="store_true", help="required: overwrites stored settings")
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
    if not args.verbose:  # httpx logs every request at INFO: one line per poll
        logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        if args.command == "discover":
            asyncio.run(discover(args.broadcast))
            return 0
        if args.command == "run" and args.replay:
            if args.speed <= 0:
                print("--speed must be positive", file=sys.stderr)
                return 2
            asyncio.run(run_replay(load_config(args.config), args.replay, args.speed, args.fresh))
            return 0
        # run, test-effect and config use the stored settings (seeded from the file on first start)
        service, store = open_settings(args.config)
        try:
            if args.command == "run":
                run_until_signal(run_live(service, store, args.dry_run))
                return 0
            if args.command == "config":
                return config_command(args, service)
            return asyncio.run(test_effect(service.config, args.team, args.dry_run))
        finally:
            store.close()
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
