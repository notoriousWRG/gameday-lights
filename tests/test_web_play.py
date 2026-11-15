import asyncio

from app.bulbs.base import DryRunBulb
from app.store import Store
from app.watcher import WatcherStats
from app.web.status import create_app
from tests.support import (
    HDR,
    NOW,
    Recorder,
    cfg,
    client,
    make,
    page_text,
    valid_strip_cfg,
)


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

TEAM_BODY = {"league": "nfl", "id": "9", "bulbs": ["lamp"],
             "color": "#00ff00", "alt_color": "#ffb612"}


def make_team_test(bulb, colors=None, clock=None):
    from app.dispatch.dispatcher import (
        Dispatcher,
        make_bulb_pulse,
        make_planner,
        make_team_test,
    )

    store = Store()
    config = cfg()
    colors = colors or {}
    dispatcher = Dispatcher(store, {"lamp": bulb}, make_planner(config, colors, store))
    kwargs = {"clock": clock} if clock else {}
    return create_app(store, config, WatcherStats(started_at=NOW), {"lamp": bulb}, False,
                      now=lambda: NOW, dispatcher=dispatcher,
                      pulse_pattern=make_bulb_pulse(config, colors),
                      team_test=make_team_test(config, colors), **kwargs)


async def test_team_test_plays_the_edited_colors_on_the_bulbs_and_restores():
    bulb = Recorder("lamp")
    async with client(make_team_test(bulb)) as c:
        r = await c.post("/api/teams/test", headers=HDR, json=TEAM_BODY)
    assert r.status_code == 200 and [b["name"] for b in r.json()["bulbs"]] == ["lamp"]
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
        html = await page_text(c)
    assert "Pulse" in html and "X-Gameday" in html and "innerHTML" not in html


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


def make_state_app(bulb=None, clock=None):
    bulb = bulb or DryRunBulb("lamp")
    from app.dispatch.dispatcher import Dispatcher, make_bulb_pulse, make_planner

    store = Store()
    config = cfg()
    dispatcher = Dispatcher(store, {"lamp": bulb}, make_planner(config, {}, store))
    kwargs = {"clock": clock} if clock else {}
    return create_app(store, config, WatcherStats(started_at=NOW), {"lamp": bulb}, False,
                      now=lambda: NOW, dispatcher=dispatcher,
                      pulse_pattern=make_bulb_pulse(config, {}), **kwargs), bulb


async def test_state_put_sets_the_bulb_and_get_reads_it_back():
    app, bulb = make_state_app()
    async with client(app) as c:
        r = await c.put("/api/bulbs/lamp/state", headers=HDR,
                        json={"color": "#ff8800", "brightness": 80})
        assert r.status_code == 200 and r.json()["applied"]["color"] == "#ff8800"
        got = (await c.get("/api/bulbs/lamp/state")).json()
    assert got["color"] == "#ff8800" and got["brightness"] == 80 and got["on"] is True
    assert bulb.calls[0][0] == "set_state"


async def test_state_put_checks_header_body_and_ranges():
    app, _ = make_state_app()
    async with client(app) as c:
        url = "/api/bulbs/lamp/state"
        assert (await c.put(url, json={"on": False})).status_code == 403
        assert (await c.put("/api/bulbs/nope/state", headers=HDR,
                            json={"on": False})).status_code == 404
        for bad in ({}, [], {"nope": 1}, {"on": "yes"}, {"brightness": "high"},
                    {"brightness": True}):
            assert (await c.put(url, headers=HDR, json=bad)).status_code == 400, bad
        for bad in ({"brightness": 0}, {"brightness": 300}, {"color_temp_k": 50},
                    {"color": "#00ff00", "color_temp_k": 3000}):
            assert (await c.put(url, headers=HDR, json=bad)).status_code == 422, bad


async def test_state_changes_are_rate_limited_per_bulb_and_blocked_during_effects():
    t = [0.0]
    gate = asyncio.Event()
    app, _ = make_state_app(Recorder("lamp", gate=gate), clock=lambda: t[0])
    async with client(app) as c:
        url = "/api/bulbs/lamp/state"
        assert (await c.put(url, headers=HDR, json={"brightness": 10})).status_code == 200
        assert (await c.put(url, headers=HDR, json={"brightness": 20})).status_code == 429
        t[0] = 1.0
        assert (await c.put(url, headers=HDR, json={"brightness": 20})).status_code == 200
        # an effect is playing (gate held): manual changes are refused, not queued behind it
        pulse = asyncio.create_task(c.post("/api/bulbs/lamp/pulse", headers=HDR))
        await asyncio.sleep(0.05)
        t[0] = 5.0
        assert (await c.put(url, headers=HDR, json={"brightness": 30})).status_code == 409
        gate.set()
        await pulse


async def test_team_test_plays_each_bulb_its_own_effect_and_reports_per_bulb():
    from app.bulbs.base import DryRunBulb
    from app.dispatch.dispatcher import (
        Dispatcher,
        make_bulb_pulse,
        make_planner,
        make_team_test,
    )

    store = Store()
    config = valid_strip_cfg()
    lamp, strip = Recorder("lamp"), Recorder("strip")
    bulbs = {"lamp": lamp, "strip": strip}
    dispatcher = Dispatcher(store, bulbs, make_planner(config, {}, store))
    app = create_app(store, config, WatcherStats(started_at=NOW), bulbs, False, now=lambda: NOW,
                     dispatcher=dispatcher, pulse_pattern=make_bulb_pulse(config, {}),
                     team_test=make_team_test(config, {}))
    body = {"league": "nfl", "id": "9", "bulbs": ["lamp", "strip"],
            "color": "#112233", "alt_color": None}
    async with client(app) as c:
        r = await c.post("/api/teams/test", headers=HDR, json=body)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert [b["name"] for b in r.json()["bulbs"]] == ["lamp", "strip"]
    assert [x[0] for x in lamp.calls][:2] == ["snapshot", "set_color"]  # pulse on the lamp
    assert lamp.calls[1][1] == (0x11, 0x22, 0x33)  # the edited color, not the saved green
    assert [x[0] for x in strip.calls] == ["snapshot", "play_segments", "restore"]  # chase
    assert isinstance(lamp, DryRunBulb)


async def test_team_test_one_bulb_failing_does_not_stop_the_other():
    from app.dispatch.dispatcher import (
        Dispatcher,
        make_bulb_pulse,
        make_planner,
        make_team_test,
    )

    store = Store()
    config = valid_strip_cfg()
    bulbs = {"lamp": Recorder("lamp", fail=True), "strip": Recorder("strip")}
    dispatcher = Dispatcher(store, bulbs, make_planner(config, {}, store))
    app = create_app(store, config, WatcherStats(started_at=NOW), bulbs, False, now=lambda: NOW,
                     dispatcher=dispatcher, pulse_pattern=make_bulb_pulse(config, {}),
                     team_test=make_team_test(config, {}))
    body = {"league": "nfl", "id": "9", "bulbs": ["lamp", "strip"],
            "color": None, "alt_color": None}
    async with client(app) as c:
        r = await c.post("/api/teams/test", headers=HDR, json=body)
    out = {b["name"]: b for b in r.json()["bulbs"]}
    assert r.status_code == 200 and r.json()["ok"] is False
    assert out["lamp"]["ok"] is False and "bulb error" in out["lamp"]["error"]
    assert out["strip"]["ok"] is True


async def test_reading_a_bulb_that_does_not_answer_gives_up_with_a_clear_message(monkeypatch):
    from app.web import routes_bulbs

    class Hung(DryRunBulb):
        async def current_state(self):
            await asyncio.sleep(60)

    monkeypatch.setattr(routes_bulbs, "STATE_READ_TIMEOUT_S", 0.05)
    app, _ = make_state_app(Hung("lamp"))
    async with client(app) as c:
        r = await c.get("/api/bulbs/lamp/state")
    assert r.status_code == 504 and "not answering" in r.json()["detail"]
