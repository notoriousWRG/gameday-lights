import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.bulbs.base import DryRunBulb
from app.config import BulbConfig, Config, GeneralConfig, TeamConfig
from app.effects import EffectConfig
from app.store import Event, Game, Store, dedupe_key
from app.watcher import WatcherStats
from app.web import status as web
from app.web.status import BulbPings, create_app

NOW = datetime(2026, 11, 8, 21, 40, tzinfo=UTC)


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


async def test_status_json_shape():
    async with client(make()) as c:
        s = (await c.get("/api/status")).json()
    assert s["mode"] == "live" and s["delay_s"] == 45 and s["uptime_s"] == 3600
    assert s["bulbs"] == [{"name": "lamp", "ip": "10.0.0.5", "ping_ms": 0}]
    assert s["watcher"]["watching"] == ["GB @ NE"] and s["watcher"]["polls"] == 5
    sched = {g["id"]: g for g in s["schedule"]}
    assert [g["id"] for g in s["schedule"]] == ["g8", "g9", "g0", "g1", "g2"]  # chronological
    assert (sched["g0"]["us"], sched["g0"]["opp"], sched["g0"]["home"]) == ("GB", "MIN", False)
    g0 = sched["g0"]
    assert (g0["us_score"], g0["opp_score"], g0["result"]) == (27, 20, "W")
    assert sched["g9"]["result"] == "L" and sched["g8"]["result"] == "T"
    live, nxt = sched["g1"], sched["g2"]
    assert (live["status"], live["us_score"], live["opp_score"]) == ("in", 10, 7)
    assert live["result"] is None  # no W/L until it is final
    assert (nxt["home"], nxt["us_score"], nxt["result"]) == (True, None, None)
    (e,) = s["events"]
    assert (e["game"], e["team"], e["label"], e["delta"], e["status"]) == (
        "GB @ NE", "GB", "TD", 6, "fired")
    assert e["fire_delay_s"] == 46


async def test_dry_run_mode_and_unreachable_bulb():
    async with client(make(Down("lamp"), dry_run=True)) as c:
        s = (await c.get("/api/status")).json()
    assert s["mode"] == "dry_run" and s["bulbs"][0]["ping_ms"] is None


async def test_page_served_and_has_no_html_injection_paths():
    async with client(make()) as c:
        r = await c.get("/")
    assert r.status_code == 200 and "Gameday Lights" in r.text
    assert "innerHTML" not in r.text  # server strings are only ever set via textContent


async def test_no_write_endpoints_or_docs():
    async with client(make()) as c:
        assert (await c.post("/api/status")).status_code == 405
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404


async def test_pings_are_cached_then_refreshed():
    calls = []

    class Counting(DryRunBulb):
        async def ping(self):
            calls.append(1)
            return 0.01

    t = [0.0]
    p = BulbPings({"lamp": Counting("lamp")}, clock=lambda: t[0])
    await p.get()
    t[0] = 29
    await p.get()
    assert len(calls) == 1
    t[0] = 31
    await p.get()
    assert len(calls) == 2


async def test_ping_timeout_counts_as_unreachable(monkeypatch):
    import asyncio

    class Slow(DryRunBulb):
        async def ping(self):
            await asyncio.sleep(10)

    monkeypatch.setattr(web, "PING_TIMEOUT_S", 0.05)
    assert await BulbPings({"lamp": Slow("lamp")}).get() == {"lamp": None}


async def test_serve_status_survives_bind_failure(caplog):
    import socket

    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    port = blocker.getsockname()[1]
    try:
        app = make()
        await web.serve_status(app, "127.0.0.1", port)  # must return, not raise or exit
    finally:
        blocker.close()
    assert re.search("could not start", caplog.text)


async def test_serve_status_stops_cleanly_when_cancelled(capfd):
    import asyncio

    task = asyncio.ensure_future(web.serve_status(make(), "127.0.0.1", 0))
    await asyncio.sleep(0.5)  # let uvicorn start
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # uvicorn logs to stderr without propagating, so caplog can't see a shutdown traceback
    assert "Traceback" not in capfd.readouterr().err


# --- pulse button ---------------------------------------------------------------------

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


def make_pulse(bulb, clock=None):
    from app.dispatch.dispatcher import Dispatcher, make_bulb_pulse, make_planner

    store = Store()
    config = cfg()
    dispatcher = Dispatcher(store, {"lamp": bulb}, make_planner(config, {}, store))
    kwargs = {"clock": clock} if clock else {}
    app = create_app(store, config, WatcherStats(started_at=NOW), {"lamp": bulb}, False,
                     now=lambda: NOW, dispatcher=dispatcher,
                     pulse_pattern=make_bulb_pulse(config, {}), **kwargs)
    return app, store


async def test_pulse_requires_custom_header():
    app, _ = make_pulse(Recorder("lamp"))
    async with client(app) as c:
        r = await c.post("/api/bulbs/lamp/pulse")
        assert r.status_code == 403
        # a cross-site form post: right method, wrong (simple) content type, no custom header
        r = await c.post("/api/bulbs/lamp/pulse", data={"x": "1"})
        assert r.status_code == 403


async def test_pulse_unknown_bulb_404():
    app, _ = make_pulse(Recorder("lamp"))
    async with client(app) as c:
        assert (await c.post("/api/bulbs/nope/pulse", headers=HDR)).status_code == 404


async def test_pulse_plays_snapshot_flash_restore_and_writes_no_event():
    bulb = Recorder("lamp")
    app, store = make_pulse(bulb)
    async with client(app) as c:
        r = await c.post("/api/bulbs/lamp/pulse", headers=HDR)
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True and body["duration_s"] == 6.0
    kinds = [x[0] for x in bulb.calls]
    assert kinds[0] == "snapshot" and kinds[-1] == "restore"
    assert kinds.count("set_color") == 10  # the default 5-pulse pattern, via the dispatcher
    assert store.recent_events(5) == []  # a pulse is not a game event


async def test_pulse_cooldown_counts_from_the_end_of_the_last_pulse():
    t = [100.0]
    app, _ = make_pulse(Recorder("lamp"), clock=lambda: t[0])
    async with client(app) as c:
        assert (await c.post("/api/bulbs/lamp/pulse", headers=HDR)).status_code == 200
        t[0] = 105
        r = await c.post("/api/bulbs/lamp/pulse", headers=HDR)
        assert r.status_code == 429 and "wait 5s" in r.json()["detail"]
        t[0] = 110.5
        assert (await c.post("/api/bulbs/lamp/pulse", headers=HDR)).status_code == 200


async def test_pulse_while_pulsing_is_409():
    gate = asyncio.Event()
    app, _ = make_pulse(Recorder("lamp", gate=gate))
    async with client(app) as c:
        first = asyncio.ensure_future(c.post("/api/bulbs/lamp/pulse", headers=HDR))
        await asyncio.sleep(0.05)  # first request is now inside the flash
        second = await c.post("/api/bulbs/lamp/pulse", headers=HDR)
        gate.set()
        assert second.status_code == 409
        assert (await first).status_code == 200


async def test_pulse_failure_is_502_still_restores_and_starts_cooldown():
    bulb = Recorder("lamp", fail=True)
    app, _ = make_pulse(bulb)
    async with client(app) as c:
        r = await c.post("/api/bulbs/lamp/pulse", headers=HDR)
        assert r.status_code == 502 and "bulb died" in r.json()["detail"]
        assert bulb.calls[-1][0] == "restore"  # snapshot/restore even on failure
        assert (await c.post("/api/bulbs/lamp/pulse", headers=HDR)).status_code == 429


def make_team_test(bulb, colors=None, clock=None):
    from app.dispatch.dispatcher import (
        Dispatcher,
        make_bulb_pulse,
        make_planner,
        make_team_pulse,
    )

    store = Store()
    config = cfg()
    colors = colors or {}
    dispatcher = Dispatcher(store, {"lamp": bulb}, make_planner(config, colors, store))
    kwargs = {"clock": clock} if clock else {}
    return create_app(store, config, WatcherStats(started_at=NOW), {"lamp": bulb}, False,
                      now=lambda: NOW, dispatcher=dispatcher,
                      pulse_pattern=make_bulb_pulse(config, colors),
                      team_pulse=make_team_pulse(config, colors), **kwargs)


TEAM_BODY = {"league": "nfl", "id": "9", "bulbs": ["lamp"],
             "color": "#00ff00", "alt_color": "#ffb612"}


async def test_team_test_plays_the_edited_colors_on_the_bulbs_and_restores():
    bulb = Recorder("lamp")
    async with client(make_team_test(bulb)) as c:
        r = await c.post("/api/teams/test", headers=HDR, json=TEAM_BODY)
    assert r.status_code == 200 and r.json()["bulbs"] == ["lamp"]
    colors = [x[1] for x in bulb.calls if x[0] == "set_color"]
    assert colors[0] == (0, 255, 0) and colors[1] == (255, 182, 18) and len(colors) == 10
    assert bulb.calls[0][0] == "snapshot" and bulb.calls[-1][0] == "restore"


async def test_team_test_falls_back_to_espn_colors_when_the_team_has_none():
    bulb = Recorder("lamp")
    body = {"league": "nfl", "id": "9", "bulbs": ["lamp"], "color": None, "alt_color": None,
            "espn_color": "#112233", "espn_alt_color": "#445566"}
    async with client(make_team_test(bulb)) as c:
        assert (await c.post("/api/teams/test", headers=HDR, json=body)).status_code == 200
    colors = [x[1] for x in bulb.calls if x[0] == "set_color"]
    assert colors[:2] == [(0x11, 0x22, 0x33), (0x44, 0x55, 0x66)]


async def test_team_test_guards_and_bad_input():
    async with client(make_team_test(Recorder("lamp"))) as c:
        assert (await c.post("/api/teams/test", json=TEAM_BODY)).status_code == 403
        assert (await c.post("/api/teams/test", headers=HDR, json={})).status_code == 400
        for bad in ({"bulbs": []}, {"color": "green"}, {"bulbs": [3]}):
            r = await c.post("/api/teams/test", headers=HDR, json={**TEAM_BODY, **bad})
            assert r.status_code == 400, bad
        r = await c.post("/api/teams/test", headers=HDR, json={**TEAM_BODY, "bulbs": ["nope"]})
        assert r.status_code == 404


async def test_team_test_shares_the_pulse_cooldown():
    t = [100.0]
    async with client(make_team_test(Recorder("lamp"), clock=lambda: t[0])) as c:
        assert (await c.post("/api/teams/test", headers=HDR, json=TEAM_BODY)).status_code == 200
        t[0] = 103
        assert (await c.post("/api/teams/test", headers=HDR, json=TEAM_BODY)).status_code == 429
        assert (await c.post("/api/bulbs/lamp/pulse", headers=HDR)).status_code == 429


async def test_no_pulse_endpoint_without_a_dispatcher():
    async with client(make()) as c:
        assert (await c.post("/api/bulbs/lamp/pulse", headers=HDR)).status_code in (404, 405)


async def test_page_has_pulse_button_wired_with_the_header():
    async with client(make()) as c:
        html = (await c.get("/")).text
    assert "Pulse" in html and "X-Gameday" in html and "innerHTML" not in html


async def test_schedule_row_without_team_data_falls_back_to_name():
    store = Store()  # a legacy row with no home/away info
    store.upsert_game(Game("old", "nfl", "GB @ ATL", NOW, "post"))
    from app.web.status import schedule_rows

    (row,) = schedule_rows(store, cfg())
    assert row["name"] == "GB @ ATL" and row["us"] is None and row["result"] is None


async def test_page_is_read_once_at_startup_so_it_matches_the_running_api(tmp_path, monkeypatch):
    page = tmp_path / "status.html"
    page.write_text("<html>version A</html>")
    monkeypatch.setattr(web, "PAGE", page)
    app = make()
    page.write_text("<html>version B</html>")  # an update on disk, server not restarted
    async with client(app) as c:
        assert "version A" in (await c.get("/")).text


# --- scoreboard card ------------------------------------------------------------------

def live_game(state="in", detail="4:21 - 3rd", ended=None, gid="g1", us_home=False):
    side = lambda abbr, score: {  # noqa: E731
        "abbr": abbr, "name": abbr, "score": score, "record": "6-3", "linescores": [3, 7]}
    return {
        "game_id": gid, "name": "GB @ NE", "state": state, "status_name": "STATUS_X",
        "detail": detail, "clock": "4:21", "period": 3, "home": side("NE", 7),
        "away": side("GB", 10), "broadcast": "CBS", "venue": "Gillette Stadium",
        "situation": None, "updated_at": NOW, "ended_at": ended,
    }


def card(live=(), watching=(), schedule=None, now=NOW, interval=15.0, hold=30.0):
    from dataclasses import replace

    from app.web.status import schedule_rows, scoreboard_card

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", NOW - timedelta(minutes=30), "in",
                           "NE", 7, "GB", 10))
    store.upsert_game(Game("g2", "nfl", "MIN @ GB", NOW + timedelta(days=7), "pre",
                           "GB", None, "MIN", None))
    store.upsert_game(Game("g3", "nfl", "GB @ LAR", NOW + timedelta(days=17), "pre",
                           "LAR", None, "GB", None))
    config = cfg()
    config = replace(config, web=replace(config.web, final_hold_min=hold))
    stats = WatcherStats(started_at=NOW, watching_ids=list(watching), poll_interval_s=interval,
                         last_poll_at=NOW, live={g["game_id"]: g for g in live})
    rows = schedule if schedule is not None else schedule_rows(store, config)
    return scoreboard_card(store, config, stats, now, rows)


def test_scoreboard_live_shows_game_and_polling_state():
    c = card(live=[live_game()], watching=["g1"])
    assert c["mode"] == "live" and c["polling"]["active"] and c["polling"]["interval_s"] == 15
    (g,) = c["games"]
    assert (g["detail"], g["clock"], g["league"]) == ("4:21 - 3rd", "4:21", "nfl")
    assert (g["away"]["abbr"], g["away"]["us"], g["home"]["us"]) == ("GB", True, False)
    assert g["start_utc"] is not None and [n["id"] for n in c["next_games"]] == ["g2"]


def test_scoreboard_pre_game_inside_the_lead_window():
    c = card(live=[live_game(state="pre", detail="Sun 4:25 PM")], watching=["g1"], interval=60)
    assert c["mode"] == "pre"
    assert (c["polling"]["interval_s"], c["polling"]["lead_min"]) == (60, 10)


def test_scoreboard_final_held_then_falls_back_to_next_game():
    ended = NOW - timedelta(minutes=10)
    final = live_game(state="post", detail="Final", ended=ended)
    c = card(live=[final], interval=None)
    assert c["mode"] == "final" and c["games"][0]["state"] == "post"
    assert c["polling"]["active"] is False
    later = card(live=[final], interval=None, now=NOW + timedelta(minutes=21))
    assert later["mode"] == "next" and later["games"] == []
    assert card(live=[final], hold=0)["mode"] == "next"  # 0 = drop at once


def test_scoreboard_next_game_this_week_or_not():
    c = card()
    assert c["mode"] == "next" and [n["id"] for n in c["next_games"]] == ["g2"]
    assert c["next_games"][0]["in_week"] is True and c["polling"]["active"] is False
    far = card(now=NOW - timedelta(days=3))  # next game is now 10 days out
    assert far["next_games"][0]["id"] == "g2" and far["next_games"][0]["in_week"] is False


def test_scoreboard_idle_with_nothing_scheduled():
    c = card(schedule=[])
    assert c["mode"] == "idle" and c["next_games"] == [] and c["games"] == []


def test_scoreboard_live_game_is_listed_first_and_not_repeated_as_next():
    c = card(live=[live_game(state="pre", gid="g1"), live_game(gid="g9")], watching=["g1", "g9"])
    assert c["mode"] == "live" and c["games"][0]["id"] == "g9"
    assert "g1" not in {n["id"] for n in c["next_games"]}


async def test_status_includes_scoreboard_block():
    async with client(make()) as c:
        s = (await c.get("/api/status")).json()
    assert s["scoreboard"]["mode"] in ("next", "idle") and "polling" in s["scoreboard"]


# --- several followed teams -----------------------------------------------------------

def multi_cfg():
    return Config(
        GeneralConfig(True, "x.db", delay_s=45),
        (BulbConfig("lamp", "10.0.0.5"),),
        (TeamConfig("nfl", "9", "GB", ("lamp",), color=(0, 255, 0)),
         TeamConfig("nfl", "3", "CHI", ("lamp",)),
         TeamConfig("nfl", "23", "PIT", ("lamp",)),
         TeamConfig("nhl", "16", "PIT", ("lamp",))),
        EffectConfig(),
    )


def multi_store():
    store = Store()
    d = NOW - timedelta(days=7)
    # both teams followed
    store.upsert_game(Game("g1", "nfl", "GB @ CHI", d, "post", "CHI", 17, "GB", 24))
    store.upsert_game(Game("g2", "nfl", "PIT @ BAL", d + timedelta(days=1), "post",
                           "BAL", 10, "PIT", 20))
    store.upsert_game(Game("g3", "nhl", "PIT @ NYR", NOW + timedelta(days=1), "pre",
                           "NYR", None, "PIT", None))
    store.upsert_game(Game("g4", "nfl", "BAL @ CLE", d, "post", "CLE", 3, "BAL", 6))  # unfollowed
    store.upsert_game(Game("g5", "nfl", "legacy", d, "post"))  # no team data (old row)
    return store


def test_team_entries_key_label_color_and_pit_collision():
    from app.web.status import team_entries

    teams = {t["key"]: t for t in team_entries(multi_cfg())}
    assert set(teams) == {"nfl:GB", "nfl:CHI", "nfl:PIT", "nhl:PIT"}
    assert teams["nfl:GB"]["label"] == "GB" and teams["nfl:GB"]["color"] == "#00ff00"
    assert teams["nfl:CHI"]["color"] is None
    assert teams["nfl:PIT"]["label"] == "PIT · NFL" and teams["nhl:PIT"]["label"] == "PIT · NHL"


def test_schedule_has_one_row_per_followed_team_from_that_teams_side():
    from app.web.status import schedule_rows

    rows = schedule_rows(multi_store(), multi_cfg())
    by = {(r["id"], r["team_key"]): r for r in rows}
    # two followed teams in one game: a row on each schedule, each from its own side
    gb, chi = by[("g1", "nfl:GB")], by[("g1", "nfl:CHI")]
    assert (gb["us"], gb["opp"], gb["home"]) == ("GB", "CHI", False)
    assert (gb["result"], gb["us_score"], gb["opp_score"]) == ("W", 24, 17)
    assert (chi["us"], chi["opp"], chi["home"]) == ("CHI", "GB", True)
    assert (chi["result"], chi["us_score"], chi["opp_score"]) == ("L", 17, 24)
    # same abbreviation, different league: kept apart
    assert by[("g2", "nfl:PIT")]["result"] == "W"
    assert ("g3", "nhl:PIT") in by and ("g3", "nfl:PIT") not in by
    assert by[("g3", "nhl:PIT")]["status"] == "pre" and by[("g3", "nhl:PIT")]["result"] is None


def test_unfollowed_games_hidden_and_legacy_rows_have_no_team():
    from app.web.status import schedule_rows

    rows = schedule_rows(multi_store(), multi_cfg())
    assert "g4" not in {r["id"] for r in rows}  # a team that is no longer followed
    (legacy,) = [r for r in rows if r["id"] == "g5"]
    assert legacy["team_key"] is None and legacy["us"] is None


def test_rows_stay_in_chronological_order():
    from app.web.status import schedule_rows

    starts = [r["start_utc"] for r in schedule_rows(multi_store(), multi_cfg())]
    assert starts == sorted(starts)


def test_scoreboard_us_flag_is_per_league():
    from app.web.status import scoreboard_card

    store = Store()
    # an NHL team that happens to share the abbreviation "GB"
    store.upsert_game(Game("n1", "nhl", "GB @ NYR", NOW, "in", "NYR", 1, "GB", 2))
    live = live_game(gid="n1")
    stats = WatcherStats(started_at=NOW, watching_ids=["n1"], poll_interval_s=15.0,
                         live={"n1": live})
    c = scoreboard_card(store, cfg(), stats, NOW, [])  # cfg() follows nfl:GB only
    assert c["games"][0]["away"]["abbr"] == "GB" and c["games"][0]["away"]["us"] is False


async def test_page_has_team_filter_and_survives_blocked_storage():
    async with client(make()) as c:
        html = (await c.get("/")).text
    assert "sched-filter" in html and "gl-sched-filter" in html and "teamcol" in html
    assert "try {" in html and "innerHTML" not in html


# --- live apply -------------------------------------------------------------------------------

async def test_page_follows_the_current_config_and_bulb_list_without_a_restart():
    from dataclasses import replace

    from app.config import BulbConfig

    box = {"cfg": cfg(), "bulbs": {"lamp": DryRunBulb("lamp")}}
    store = Store()
    app = create_app(store, lambda: box["cfg"], WatcherStats(started_at=NOW), lambda: box["bulbs"],
                     False, now=lambda: NOW)
    async with client(app) as c:
        s = (await c.get("/api/status")).json()
        assert [b["name"] for b in s["bulbs"]] == ["lamp"] and s["delay_s"] == 45
        # a settings edit: a second bulb and a new delay
        box["cfg"] = replace(box["cfg"], bulbs=(*box["cfg"].bulbs, BulbConfig("den", "10.0.0.9")),
                             general=replace(box["cfg"].general, delay_s=20))
        box["bulbs"] = {**box["bulbs"], "den": DryRunBulb("den")}
        s = (await c.get("/api/status")).json()
        assert [b["name"] for b in s["bulbs"]] == ["lamp", "den"] and s["delay_s"] == 20
        assert all(b["ping_ms"] == 0 for b in s["bulbs"])  # the new bulb was pinged straight away


async def test_pulse_endpoint_follows_a_bulb_added_after_startup():
    from app.dispatch.dispatcher import Dispatcher, make_bulb_pulse, make_planner

    store = Store()
    config = cfg()
    lamp = Recorder("lamp")
    dispatcher = Dispatcher(store, {"lamp": lamp}, make_planner(config, {}, store))
    app = create_app(store, config, WatcherStats(started_at=NOW), lambda: dispatcher.bulbs, False,
                     now=lambda: NOW, dispatcher=dispatcher,
                     pulse_pattern=make_bulb_pulse(config, {}))
    async with client(app) as c:
        assert (await c.post("/api/bulbs/den/pulse", headers=HDR)).status_code == 404
        den = Recorder("den")
        dispatcher.set_bulbs({"lamp": lamp, "den": den})
        assert (await c.post("/api/bulbs/den/pulse", headers=HDR)).status_code == 200
        assert den.calls and den.calls[0][0] == "snapshot"


async def test_page_has_nav_and_the_teams_screen_wired_to_the_guarded_api():
    async with client(make()) as c:
        html = (await c.get("/")).text
    for needle in ('id="tab-teams"', 'href="#/teams"', 'id="view-teams"', 'api/teams/search',
                   'api/settings/teams', '"If-Match"', '"X-Gameday"', "beforeunload",
                   "clearErrors", "Load latest", "api/teams/test", "testTeam"):
        assert needle in html, needle
    assert "innerHTML" not in html  # ESPN names and settings text only ever go in as text


async def test_page_has_the_settings_screen_on_the_shared_section_editor():
    async with client(make()) as c:
        html = (await c.get("/")).text
    for needle in ('id="tab-settings"', 'href="#/settings"', 'id="view-settings"', "const ROUTES",
                   "sectionEditor", 'section: "household"', "delay_s", "api/settings/${ed.section}",
                   '"If-Match"', '"X-Gameday"', "Load latest", "beforeunload"):
        assert needle in html, needle
    assert "innerHTML" not in html


async def test_page_has_the_effects_screen_with_a_test_button_on_the_pulse_path():
    async with client(make()) as c:
        html = (await c.get("/")).text
    for needle in ('id="tab-effects"', 'href="#/effects"', 'id="view-effects"',
                   'section: "effects"', "effects.score.pulses", "FLASH_CAP", "Use team colors",
                   "Save to test your changes", "pulse(testBulb)",
                   "api/bulbs/${encodeURIComponent(name)}/pulse"):
        assert needle in html, needle
    assert "innerHTML" not in html


async def test_page_has_the_advanced_screen_with_the_poll_floor_and_machine_note():
    async with client(make()) as c:
        html = (await c.get("/")).text
    for needle in ('id="tab-advanced"', 'href="#/advanced"', 'id="view-advanced"',
                   'section: "advanced"', "ADV_DEFAULTS", "poll_live_s", "min: 10",
                   "Reset to defaults", "dispatch_enabled", 'href="#/advanced">Advanced timings'):
        assert needle in html, needle
    assert "innerHTML" not in html


async def test_page_has_the_bulbs_screen_with_write_only_keys_and_discovery():
    async with client(make()) as c:
        html = (await c.get("/")).text
    for needle in ('id="tab-bulbs"', 'href="#/bulbs"', 'id="view-bulbs"', 'section: "bulbs"',
                   "api/bulbs/discover", "bulbPayload", 'type = "password"', "has_signing_key",
                   "Find bulbs on the network", "Add by IP", "Remove key",
                   "/rename", "Teams using it"):
        assert needle in html, needle
    assert "innerHTML" not in html
    assert "config.toml for now" not in html


# --- next game for every followed team -------------------------------------------------------

def teams_cfg(*teams):
    """A config following (league, id, abbr) teams, all on one bulb."""
    return Config(
        GeneralConfig(True, "x.db", delay_s=45),
        (BulbConfig("lamp", "10.0.0.5"),),
        tuple(TeamConfig(lg, tid, abbr, ("lamp",)) for lg, tid, abbr in teams),
        EffectConfig(),
    )


def next_games_for(cfg_, games, live=(), watching=(), now=NOW):
    from app.web.status import schedule_rows, scoreboard_card

    store = Store()
    for g in games:
        store.upsert_game(g)
    stats = WatcherStats(started_at=NOW, watching_ids=list(watching), poll_interval_s=15.0,
                         live={g["game_id"]: g for g in live})
    return scoreboard_card(store, cfg_, stats, now, schedule_rows(store, cfg_))


PENS = ("nhl", "16", "PIT")
PACK = ("nfl", "9", "GB")
TONIGHT = NOW + timedelta(hours=5)
SUNDAY = NOW + timedelta(days=1, hours=6)


def test_each_followed_team_gets_its_own_next_game_soonest_first():
    games = [
        Game("pens", "nhl", "PIT @ NYR", TONIGHT, "pre", "NYR", None, "PIT", None),
        Game("gb", "nfl", "GB @ NE", SUNDAY, "pre", "NE", None, "GB", None),
        Game("pens2", "nhl", "NJ @ PIT", SUNDAY + timedelta(days=2), "pre", "PIT", None,
             "NJ", None),
        Game("gb2", "nfl", "MIN @ GB", SUNDAY + timedelta(days=7), "pre", "GB", None, "MIN", None),
    ]
    c = next_games_for(teams_cfg(PACK, PENS), games)  # GB listed first, Pens play first
    assert c["mode"] == "next"
    assert [(n["id"], n["team_key"]) for n in c["next_games"]] == [
        ("pens", "nhl:PIT"), ("gb", "nfl:GB")]  # soonest first, one card per team
    pens, gb = c["next_games"]
    assert (pens["us"], pens["opp"], pens["home"]) == ("PIT", "NYR", False)
    assert (gb["us"], gb["opp"], gb["home"]) == ("GB", "NE", False)
    assert pens["in_week"] and gb["in_week"]


def test_a_team_with_nothing_upcoming_is_simply_left_out():
    games = [Game("old", "nhl", "PIT @ NYR", NOW - timedelta(days=1), "post", "NYR", 2, "PIT", 3),
             Game("gb", "nfl", "GB @ NE", SUNDAY, "pre", "NE", None, "GB", None)]
    c = next_games_for(teams_cfg(PACK, PENS), games)
    assert [n["team_key"] for n in c["next_games"]] == ["nfl:GB"]


def test_at_most_three_next_games_the_soonest_three():
    teams = [("nfl", "9", "GB"), ("nfl", "17", "NE"), ("nfl", "23", "PIT"), ("nhl", "16", "PIT")]
    games = [
        Game("g1", "nfl", "a", NOW + timedelta(days=4), "pre", "ZZZ", None, "GB", None),
        Game("g2", "nfl", "b", NOW + timedelta(days=1), "pre", "ZZZ", None, "NE", None),
        Game("g3", "nfl", "c", NOW + timedelta(days=3), "pre", "ZZZ", None, "PIT", None),
        Game("g4", "nhl", "d", NOW + timedelta(days=2), "pre", "ZZZ", None, "PIT", None),
    ]
    c = next_games_for(teams_cfg(*teams), games)
    assert [n["id"] for n in c["next_games"]] == ["g2", "g4", "g3"]  # g1 (GB, day 4) is cut


def test_a_game_between_two_followed_teams_is_one_card_on_the_first_team():
    games = [Game("derby", "nfl", "GB @ NE", SUNDAY, "pre", "NE", None, "GB", None),
             Game("ne2", "nfl", "NE @ BUF", SUNDAY + timedelta(days=7), "pre", "BUF", None,
                  "NE", None)]
    c = next_games_for(teams_cfg(PACK, ("nfl", "17", "NE")), games)
    assert [(n["id"], n["team_key"]) for n in c["next_games"]] == [("derby", "nfl:GB")]
    # NE's next game IS the derby, so its following game must not show up as "next"
    assert "ne2" not in {n["id"] for n in c["next_games"]}
    c = next_games_for(teams_cfg(("nfl", "17", "NE"), PACK), games)  # order in the list decides
    assert [(n["id"], n["team_key"]) for n in c["next_games"]] == [("derby", "nfl:NE")]


def test_while_one_team_plays_the_others_next_games_are_listed_beside_it():
    games = [Game("now", "nhl", "PIT @ NYR", NOW, "in", "NYR", 1, "PIT", 2),
             Game("gb", "nfl", "GB @ NE", SUNDAY, "pre", "NE", None, "GB", None),
             Game("later", "nhl", "NJ @ PIT", SUNDAY + timedelta(days=2), "pre", "PIT", None,
                  "NJ", None)]
    live = [live_game(gid="now")]
    c = next_games_for(teams_cfg(PACK, PENS), games, live=live, watching=["now"])
    assert c["mode"] == "live" and [g["id"] for g in c["games"]] == ["now"]
    # the Pens' next game after tonight's is theirs to show; GB's is Sunday
    assert [(n["id"], n["team_key"]) for n in c["next_games"]] == [
        ("gb", "nfl:GB"), ("later", "nhl:PIT")]


def test_next_games_use_the_leagues_in_the_key_not_just_the_abbreviation():
    games = [Game("nfl-pit", "nfl", "PIT @ BAL", SUNDAY, "pre", "BAL", None, "PIT", None)]
    c = next_games_for(teams_cfg(PENS), games)  # only the NHL PIT is followed
    assert c["next_games"] == [] and c["mode"] == "idle"


async def test_page_script_has_no_duplicate_function_names():
    """A second `function foo` silently replaces the first (this once broke the live scoreboard)."""
    import collections

    async with client(make()) as c:
        html = (await c.get("/")).text
    names = re.findall(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", html, re.M)
    assert len(names) > 20  # the pattern really is finding the page's functions
    dupes = [n for n, count in collections.Counter(names).items() if count > 1]
    assert dupes == [], f"defined more than once: {dupes}"
