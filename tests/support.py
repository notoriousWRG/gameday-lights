"""Helpers shared by the web tests: fake bulbs, small configs, app builders and page readers."""

import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.bulbs.base import DryRunBulb
from app.config import BulbConfig, Config, GeneralConfig, TeamConfig
from app.effects import EffectConfig
from app.store import Event, Game, Store, dedupe_key
from app.watcher import WatcherStats
from app.web.status import create_app

NOW = datetime(2026, 11, 8, 21, 40, tzinfo=UTC)


def full_page() -> str:
    """The page shell plus its stylesheet and scripts, read from disk."""
    from app.web.status import PAGE

    parts = [PAGE.read_text(encoding="utf-8")]
    parts += [f.read_text(encoding="utf-8") for f in sorted((PAGE.parent / "static").iterdir())]
    return "\n".join(parts)


async def page_text(c) -> str:
    """What a browser gets: the shell plus every stylesheet and script it links."""
    html = (await c.get("/")).text
    for name in re.findall(r'(?:src|href)="static/([\w.]+)"', html):
        html += (await c.get(f"/static/{name}")).text
    return html


def cfg():
    return Config(
        GeneralConfig(True, "x.db", delay_s=45),
        (BulbConfig("lamp", "10.0.0.5"),),
        (TeamConfig("nfl", "9", "GB", ("lamp",)),),
        EffectConfig(),
    )


class Down(DryRunBulb):
    async def ping(self):
        return None


def make(bulb=None, dry_run=False):
    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", NOW - timedelta(minutes=15), "in",
                           "NE", 7, "GB", 10))
    store.upsert_game(Game("g2", "nfl", "MIN @ GB", NOW + timedelta(days=7), "pre",
                           "GB", None, "MIN", None))
    store.upsert_game(Game("g0", "nfl", "GB @ MIN", NOW - timedelta(days=7), "post",
                           "MIN", 20, "GB", 27))
    store.upsert_game(Game("g9", "nfl", "GB @ CHI", NOW - timedelta(days=14), "post",
                           "CHI", 24, "GB", 17))
    store.upsert_game(Game("g8", "nfl", "GB @ DET", NOW - timedelta(days=21), "post",
                           "DET", 20, "GB", 20))
    detected = NOW - timedelta(minutes=2)
    store.insert_event(Event(dedupe_key("g1", "9", 1), "g1", "9", "score", detected,
                             detected + timedelta(seconds=45),
                             {"abbr": "GB", "label": "TD", "delta": 6},
                             fired_at=detected + timedelta(seconds=46), status="fired"))
    stats = WatcherStats(started_at=NOW - timedelta(hours=1), last_poll_at=NOW, polls=5,
                         watching=["GB @ NE"])
    bulbs = {"lamp": bulb or DryRunBulb("lamp")}
    return create_app(store, cfg(), stats, bulbs, dry_run, now=lambda: NOW)


def client(app):
    # same thread/event loop as the store, as in production (TestClient would use a worker thread)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


HDR = {"X-Gameday": "1"}


class Recorder(DryRunBulb):
    def __init__(self, name, fail=False, gate=None):
        async def nosleep(s):
            await asyncio.sleep(0)

        super().__init__(name, sleep=nosleep)
        self.fail, self.gate = fail, gate

    async def set_color(self, color, brightness=255):
        if self.gate:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("bulb died")
        await super().set_color(color, brightness)


def strip_cfg():
    from app.effects import EffectLayer

    return Config(
        GeneralConfig(True, "x.db", delay_s=45),
        (BulbConfig("lamp", "10.0.0.5"),
         BulbConfig("strip", "10.0.0.6", kind="govee", segments=20)),
        (TeamConfig("nfl", "9", "GB", ("lamp", "strip"), color=(0, 255, 0),
                    effect=EffectLayer(params={"duration_s": 4.0}),
                    fixture_effects={"strip": EffectLayer(
                        "chase", {"chunk": 5}, alt_color=(255, 140, 0))}),),
        EffectConfig(),
    )


def make_matrix(bulbs, config=None, dry_run=False):
    from app.dispatch.dispatcher import (
        Dispatcher,
        make_bulb_pulse,
        make_cell_pattern,
        make_planner,
    )

    store = Store()
    config = config or strip_cfg()
    dispatcher = Dispatcher(store, bulbs, make_planner(config, {}, store))
    return create_app(store, config, WatcherStats(started_at=NOW), bulbs, dry_run,
                      now=lambda: NOW, dispatcher=dispatcher,
                      pulse_pattern=make_bulb_pulse(config, {}),
                      cell_pattern=make_cell_pattern(config, {}))


def valid_strip_cfg():
    """strip_cfg with a team duration the 2/sec cap allows (strip_cfg is only read, not played)."""
    from dataclasses import replace

    from app.effects import EffectLayer

    config = strip_cfg()
    team = replace(config.teams[0], effect=EffectLayer(params={"duration_s": 6.0}))
    return replace(config, teams=(team,))
