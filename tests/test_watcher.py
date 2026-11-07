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


async def test_stats_track_polls_errors_and_watching():
    w, _, _, _, _ = build([make_board(), EspnError("down"), make_board()])
    assert w.stats.started_at == KICKOFF
    await w.poll_once()
    assert (w.stats.polls, w.stats.errors, w.stats.last_error) == (1, 0, None)
    assert w.stats.watching == ["GB @ NE"] and w.stats.last_ok_at == KICKOFF
    await w.poll_once()
    assert (w.stats.polls, w.stats.errors, w.stats.last_error) == (2, 1, "down")
    await w.poll_once()
    assert w.stats.last_error is None
    await w.sync_schedule()
    assert w.stats.last_sync_at is not None


def board_with_sides(home, away, state="in", name="STATUS_IN_PROGRESS", gid="g1"):
    return {"events": [{
        "id": gid, "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
        "status": {"type": {"state": state, "name": name}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": str(home), "team": {"id": "17", "abbreviation": "NE"}},
            {"homeAway": "away", "score": str(away), "team": {"id": "9", "abbreviation": "GB"}},
        ]}],
    }]}


async def test_poll_records_live_then_final_score_for_both_teams():
    w, store, _, _, _ = build([
        board_with_sides(0, 0, state="pre", name="STATUS_SCHEDULED"),
        board_with_sides(7, 10), board_with_sides(13, 20, "post", "STATUS_FINAL"),
    ], start=KICKOFF - timedelta(minutes=5))
    await w.poll_once()
    g = store.get_game("g1")
    assert (g.home_abbr, g.away_abbr) == ("NE", "GB") and g.home_score is None  # pre: no score
    await w.poll_once()
    g = store.get_game("g1")
    assert (g.status, g.home_score, g.away_score) == ("in", 7, 10)
    await w.poll_once()
    g = store.get_game("g1")
    assert (g.status, g.home_score, g.away_score) == ("post", 13, 20)


async def test_stale_schedule_never_overwrites_live_status_or_score():
    class Sched(FakeClient):
        async def team_schedule(self, league, team_id, seasontype=None):
            if seasontype == 3:
                return {"events": []}
            return {"events": [{
                "id": "g1", "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
                "competitions": [{"timeValid": True, "status": {"type": {"state": "in"}},
                                  "competitors": [
                    {"homeAway": "home", "score": {"displayValue": "3"},
                     "team": {"abbreviation": "NE"}},
                    {"homeAway": "away", "score": {"displayValue": "0"},
                     "team": {"abbreviation": "GB"}}]}]}]}

    w, store, _, _, _ = build([board_with_sides(13, 20, "post", "STATUS_FINAL")])
    await w.poll_once()
    w._client = Sched([])
    await w.sync_schedule()  # cached schedule still says: in progress, 3-0
    g = store.get_game("g1")
    assert (g.status, g.home_score, g.away_score) == ("post", 13, 20)


async def test_sync_fills_missing_scores_for_games_that_predate_the_migration():
    class Sched(FakeClient):
        async def team_schedule(self, league, team_id, seasontype=None):
            if seasontype == 3:
                return {"events": []}
            return {"events": [{
                "id": "g1", "date": "2026-11-08T21:25Z", "shortName": "GB @ NE",
                "competitions": [{"timeValid": True, "status": {"type": {"state": "post"}},
                                  "competitors": [
                    {"homeAway": "home", "score": {"displayValue": "13"},
                     "team": {"abbreviation": "NE"}},
                    {"homeAway": "away", "score": {"displayValue": "20"},
                     "team": {"abbreviation": "GB"}}]}]}]}

    w, store, _, _, _ = build([make_board()])
    store.upsert_game(Game("g1", "nfl", "GB @ NE", KICKOFF, "post"))  # old row: no scores
    w._client = Sched([])
    await w.sync_schedule()
    g = store.get_game("g1")
    assert (g.home_score, g.away_score) == (13, 20)


def rich_board(state, name, detail, gb, ne, clock="4:21", period=3):
    b = board_with_sides(ne, gb, state, name)
    ev = b["events"][0]
    ev["status"].update({"displayClock": clock, "period": period})
    ev["status"]["type"]["shortDetail"] = detail
    return b


async def test_live_details_and_polling_interval_are_exposed_for_the_page():
    w, _, _, _, _ = build([
        rich_board("pre", "STATUS_SCHEDULED", "Sun 4:25 PM", 0, 0, "0:00", 0),
        rich_board("in", "STATUS_IN_PROGRESS", "4:21 - 3rd", 10, 7),
        rich_board("in", "STATUS_HALFTIME", "Halftime", 10, 7, "0:00", 2),
    ], start=KICKOFF - timedelta(minutes=5))
    assert w.stats.poll_interval_s is None and w.stats.live == {}
    await w.poll_once()
    assert w.stats.poll_interval_s == 60 and w.stats.watching_ids == ["g1"]
    assert w.stats.live["g1"]["state"] == "pre"
    await w.poll_once()
    g = w.stats.live["g1"]
    assert (g["detail"], g["clock"], g["period"]) == ("4:21 - 3rd", "4:21", 3)
    assert (g["away"]["abbr"], g["away"]["score"], g["home"]["score"]) == ("GB", 10, 7)
    assert w.stats.poll_interval_s == 15 and g["updated_at"] == KICKOFF - timedelta(minutes=5)
    await w.poll_once()
    assert w.stats.live["g1"]["detail"] == "Halftime" and w.stats.poll_interval_s == 60


async def test_final_is_kept_with_ended_at_and_polling_stops():
    w, _, _, _, clock = build([
        rich_board("in", "STATUS_IN_PROGRESS", "0:03 - 4th", 20, 13, "0:03", 4),
        rich_board("post", "STATUS_FINAL", "Final", 20, 13, "0:00", 4),
    ])
    await w.poll_once()
    assert w.stats.live["g1"]["ended_at"] is None
    await w.poll_once()
    ended = w.stats.live["g1"]["ended_at"]
    assert w.stats.live["g1"]["state"] == "post" and ended == KICKOFF
    clock.t += timedelta(minutes=10)
    await w.poll_once()  # the game left its window: no HTTP, no polling, final kept
    assert w.stats.poll_interval_s is None and w.stats.watching_ids == []
    assert w.stats.live["g1"]["ended_at"] == ended


async def test_old_finals_are_pruned():
    w, _, _, _, clock = build([rich_board("post", "STATUS_FINAL", "Final", 20, 13, "0:00", 4)])
    await w.poll_once()
    clock.t += timedelta(hours=25)
    await w.poll_once()
    assert w.stats.live == {}


# --- live apply: settings change while running -----------------------------------------------

class Live:
    """A mutable current config, like SettingsService.config."""

    def __init__(self, cfg):
        self.cfg = cfg

    def __call__(self):
        return self.cfg


def two_team_board(gb, ne, state="in", name="STATUS_IN_PROGRESS"):
    b = board_with_sides(ne, gb, state, name)
    b["events"][0]["competitions"][0]["competitors"][0]["team"]["id"] = "17"
    return b


def live_build(frames, teams=("GB",), start=KICKOFF):
    from dataclasses import replace

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", KICKOFF, "pre", "NE", None, "GB", None))
    clock = Clock(start)
    base = config()
    team = {
        "GB": base.teams[0],
        "NE": TeamConfig("nfl", "17", "NE", ("a",)),
    }
    live = Live(replace(base, teams=tuple(team[t] for t in teams)))
    disp = Dispatcher(store, {"a": DryRunBulb("a", sleep=clock.sleep)},
                      make_planner(live, {}, store), clock.now, clock.sleep, dry_run=True)
    watcher = Watcher(live, store, FakeClient(frames), disp, clock.now, clock.sleep)
    return watcher, store, live, disp


async def test_delay_edit_applies_to_the_next_event_without_a_restart():
    from dataclasses import replace

    w, store, live, _ = live_build([board_with_sides(0, 0), board_with_sides(0, 7),
                                    board_with_sides(0, 14)])
    await w.poll_once()
    await w.poll_once()
    first = store.get_event("g1:9:1")
    assert first.due_at - first.detected_at == timedelta(seconds=45)
    live.cfg = replace(live.cfg, general=replace(live.cfg.general, delay_s=20))
    await w.poll_once()
    second = store.get_event("g1:9:2")
    assert second.due_at - second.detected_at == timedelta(seconds=20)


async def test_team_followed_mid_game_baselines_first_then_fires_on_the_next_score():
    from dataclasses import replace

    frames = [two_team_board(0, 0), two_team_board(0, 3), two_team_board(0, 10)]
    w, store, live, _ = live_build(frames, teams=("GB",))
    await w.poll_once()  # only GB followed
    live.cfg = replace(live.cfg, teams=(*live.cfg.teams, TeamConfig("nfl", "17", "NE", ("a",))))
    await w.poll_once()  # NE followed now, already at 3: baselined, nothing fires for it
    assert keys(store) == []
    await w.poll_once()  # NE scores again (3 -> 10): this one fires
    assert keys(store) == ["g1:17:1"]
    assert store.get_event("g1:17:1").detail["delta"] == 7


async def test_unfollowed_team_stops_firing_and_is_baselined_again_when_followed_back():
    from dataclasses import replace

    frames = [two_team_board(0, 0), two_team_board(0, 3), two_team_board(0, 6),
              two_team_board(0, 9), two_team_board(0, 16)]
    w, store, live, _ = live_build(frames, teams=("GB", "NE"))
    both = live.cfg
    await w.poll_once()
    await w.poll_once()
    assert keys(store) == ["g1:17:1"]  # NE 0 -> 3 fired
    live.cfg = replace(both, teams=(both.teams[0],))  # unfollow NE
    await w.poll_once()
    assert keys(store) == ["g1:17:1"]  # NE 3 -> 6 while unfollowed: nothing
    live.cfg = both  # follow NE again
    await w.poll_once()  # NE is at 9 now: baselined afresh; the gap is recorded, never fired
    assert keys(store) == ["g1:17:1", "g1:17:2"]
    assert store.get_event("g1:17:2").status == "skipped_restart"
    await w.poll_once()  # 9 -> 16: a real score again
    assert keys(store) == ["g1:17:1", "g1:17:2", "g1:17:3"]
    assert store.get_event("g1:17:3").status == "pending"


async def test_games_of_teams_nobody_follows_are_not_polled():
    w, store, live, _ = live_build([two_team_board(0, 0)], teams=("GB",))
    store.upsert_game(Game("g1", "nfl", "BUF @ MIA", KICKOFF, "pre", "MIA", None, "BUF", None))
    assert await w.poll_once() == 60
    assert w._client.calls == 0  # g1 is now a game neither GB nor NE... of nobody followed


async def test_on_config_changed_requests_a_sync_only_when_followed_teams_change():
    from dataclasses import replace

    w, _, live, _ = live_build([two_team_board(0, 0)])
    old = live.cfg
    w.on_config_changed(old, replace(old, general=replace(old.general, delay_s=5)))
    assert w._sync_requested is False
    followed_ne = (*old.teams, TeamConfig("nfl", "17", "NE", ("a",)))
    w.on_config_changed(old, replace(old, teams=followed_ne))
    assert w._sync_requested is True


async def test_run_loop_wakes_from_a_long_sleep_to_sync_a_newly_followed_team():
    class Counting(FakeClient):
        syncs = 0

        async def team_schedule(self, league, team_id, seasontype=None):
            if seasontype is None:
                self.syncs += 1
            return {"events": []}

    w, _, live, _ = live_build([two_team_board(0, 0)])
    w._client = Counting([])

    async def long_sleep(seconds):
        await asyncio.sleep(3600)  # an idle poll interval

    w._sleep = long_sleep
    task = asyncio.ensure_future(w.run())
    await asyncio.sleep(0.05)
    assert w._client.syncs == 1  # the startup sync, now asleep for an hour
    w.request_sync()
    await asyncio.sleep(0.05)
    assert w._client.syncs == 2  # woke up and synced right away
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
