import asyncio
import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.bulbs.base import DryRunBulb
from app.config import BulbConfig, Config, GeneralConfig, TeamConfig
from app.dispatch.dispatcher import Dispatcher, make_planner
from app.effects import EffectConfig
from app.espn.client import EspnError
from app.espn.replay import ReplayClient
from app.store import Game, Store
from app.watcher import Watcher

KICKOFF = datetime(2026, 11, 8, 21, 25, tzinfo=UTC)


def make_board(gb=0, ne=0, state="in", name="STATUS_IN_PROGRESS", gid="g1"):
    return {"events": [{
        "id": gid, "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
        "status": {"type": {"state": state, "name": name}},
        "competitions": [{"competitors": [
            {"score": str(gb), "team": {"id": "9", "abbreviation": "GB"}},
            {"score": str(ne), "team": {"id": "17", "abbreviation": "NE"}},
        ]}],
    }]}


class FakeClient:
    def __init__(self, frames):
        self.frames, self.calls = list(frames), 0

    async def scoreboard(self, league, date=None):
        f = self.frames[min(self.calls, len(self.frames) - 1)]
        self.calls += 1
        if isinstance(f, Exception):
            raise f
        return f

    async def team_schedule(self, league, team_id, seasontype=None):
        return {"events": []}


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    async def sleep(self, s):
        self.t += timedelta(seconds=s)


def config():
    return Config(
        GeneralConfig(True, "x.db", delay_s=45),
        (BulbConfig("a", "1.1.1.1"),),
        (TeamConfig("nfl", "9", "GB", ("a",), color=(0, 255, 0), alt_color=(255, 182, 18)),),
        EffectConfig(),
    )


def build(frames, store=None, start=KICKOFF):
    store = store or Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", KICKOFF, "pre"))
    clock = Clock(start)
    cfg = config()
    bulb = DryRunBulb("a", sleep=clock.sleep)
    disp = Dispatcher(store, {"a": bulb}, make_planner(cfg, {}, store), clock.now, clock.sleep,
                      dry_run=True)
    client = FakeClient(frames)
    return Watcher(cfg, store, client, disp, clock.now, clock.sleep), store, client, disp, clock


def keys(store):
    return sorted(r[0] for r in store.db.execute("SELECT dedupe_key FROM events"))


async def test_td_then_pat_two_events_due_45s_later():
    w, store, _, disp, clock = build([make_board(0), make_board(6), make_board(7)])
    for _ in range(3):
        await w.poll_once()
    assert keys(store) == ["g1:9:1", "g1:9:2"]
    e = store.get_event("g1:9:1")
    assert e.due_at - e.detected_at == timedelta(seconds=45)
    assert e.detail == {"old": 0, "new": 6, "delta": 6, "label": "TD", "abbr": "GB"}
    await disp.wait_idle()
    assert {store.get_event(k).status for k in keys(store)} == {"dry_run"}


async def test_decrease_stores_only_then_rescore_fires_again():
    w, store, _, disp, _ = build([make_board(0), make_board(6), make_board(0), make_board(6)])
    for _ in range(4):
        await w.poll_once()
    assert keys(store) == ["g1:9:1", "g1:9:2"]
    await disp.wait_idle()


async def test_restart_does_not_replay_and_missed_increase_is_skipped():
    store = Store()
    w1, _, _, d1, _ = build([make_board(0), make_board(6)], store)
    await w1.poll_once()
    await w1.poll_once()
    await d1.wait_idle()
    # new process, same database; game is now at 13 (a score was missed while down)
    w2, _, _, d2, _ = build([make_board(13), make_board(13)], store)
    await w2.poll_once()
    await w2.poll_once()
    await d2.wait_idle()
    assert keys(store) == ["g1:9:1", "g1:9:2"]
    assert store.get_event("g1:9:1").status == "dry_run"
    assert store.get_event("g1:9:2").status == "skipped_restart"


async def test_first_poll_in_fresh_db_is_baseline():
    w, store, _, _, _ = build([make_board(7)])
    await w.poll_once()
    assert keys(store) == []


async def test_no_http_outside_watch_window():
    w, _, client, _, _ = build([make_board()], start=KICKOFF - timedelta(hours=2))
    assert await w.poll_once() == 60
    assert client.calls == 0


async def test_poll_interval_live_vs_break_and_final_stops():
    w, store, client, _, _ = build([
        make_board(0), make_board(0, name="STATUS_HALFTIME"), make_board(3, state="post",
                                                                         name="STATUS_FINAL"),
    ])
    assert await w.poll_once() == 15
    assert await w.poll_once() == 60
    await w.poll_once()
    assert store.get_game("g1").status == "post"
    assert await w.poll_once() == 60 and client.calls == 3  # no longer watched


async def test_pregame_polls_slowly_inside_lead_window():
    w, _, client, _, _ = build([make_board(state="pre")], start=KICKOFF - timedelta(minutes=5))
    assert await w.poll_once() == 60
    assert client.calls == 1


async def test_espn_error_is_survivable():
    w, _, _, _, _ = build([EspnError("down")])
    assert await w.poll_once() == 60


async def test_sync_never_moves_status_backwards():
    class Sched(FakeClient):
        async def team_schedule(self, league, team_id, seasontype=None):
            if seasontype == 3:
                return {"events": []}
            return {"events": [{"id": "g1", "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
                                "competitions": [{"timeValid": True,
                                                  "status": {"type": {"state": "in"}}}]}]}

    w, store, _, _, _ = build([make_board()])
    store.upsert_game(Game("g1", "nfl", "GB @ NE", KICKOFF, "post"))
    w._client = Sched([])
    await w.sync_schedule()
    assert store.get_game("g1").status == "post"


async def test_replay_client_drives_watcher(tmp_path):
    for i, b in enumerate([make_board(0), make_board(6), make_board(7)], 1):
        with gzip.open(tmp_path / f"{i:04d}_20261108T210000.json.gz", "wt") as f:
            json.dump(b, f)
    client = ReplayClient(tmp_path)
    store = Store()
    clock = Clock(KICKOFF)
    cfg = config()
    disp = Dispatcher(store, {"a": DryRunBulb("a", sleep=clock.sleep)},
                      make_planner(cfg, {}, store), clock.now, clock.sleep, dry_run=True)
    w = Watcher(cfg, store, client, disp, clock.now, clock.sleep)
    await w.sync_schedule()
    assert store.get_game("g1") is not None
    while not client.finished:
        await w.poll_once()
    await disp.wait_idle()
    assert keys(store) == ["g1:9:1", "g1:9:2"]


def test_replay_requires_fixtures(tmp_path):
    with pytest.raises(FileNotFoundError):
        ReplayClient(tmp_path)


async def test_run_loop_survives_errors():
    w, _, client, _, clock = build([make_board()])

    async def boom():
        raise RuntimeError("x")

    calls = []

    async def yielding_sleep(s):
        calls.append(s)
        await asyncio.sleep(0)

    w.poll_once = boom
    w._sleep = yielding_sleep
    task = asyncio.create_task(w.run())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) > 1 and calls[0] == 60  # errors are logged and the loop keeps going


async def test_logs_window_open_and_status_changes(caplog):
    caplog.set_level("INFO", logger="app.watcher")
    w, _, _, _, _ = build([
        make_board(0, state="pre", name="STATUS_SCHEDULED"), make_board(0, state="pre",
                                                                         name="STATUS_SCHEDULED"),
        make_board(0), make_board(0), make_board(0, name="STATUS_HALFTIME"),
        make_board(3, state="post", name="STATUS_FINAL"),
    ], start=KICKOFF - timedelta(minutes=5))
    for _ in range(6):
        await w.poll_once()
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.watcher"]
    assert msgs == [
        "watching GB @ NE (kickoff 2026-11-08 21:25 UTC); polling started",
        "GB @ NE: STATUS_SCHEDULED",
        "GB @ NE: STATUS_IN_PROGRESS",
        "GB @ NE: STATUS_HALFTIME",
        "GB FG 0->3 (g1:9:1) [pending]",
        "GB @ NE: STATUS_FINAL",
    ]
