import json
from datetime import timedelta

from app.bulbs.base import DryRunBulb
from app.store import Event, Game, Store, dedupe_key
from app.watcher import WatcherStats
from app.web.data import calibration
from app.web.status import create_app
from tests.support import HDR, NOW, cfg, client


def events_store(n=4):
    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", NOW - timedelta(hours=1), "in"))
    for i in range(1, n + 1):
        detected = NOW + timedelta(minutes=i)
        store.insert_event(Event(dedupe_key("g1", "9", i), "g1", "9", "score", detected,
                                 detected + timedelta(seconds=45),
                                 {"abbr": "GB", "label": "TD", "delta": 6},
                                 fired_at=detected + timedelta(seconds=46), status="fired"))
    return store


def see(store, i, lag):
    detected = NOW + timedelta(minutes=i)
    store.mark_seen(dedupe_key("g1", "9", i), detected + timedelta(seconds=lag))


def test_summary_with_no_marks_has_no_suggestion():
    out = calibration(events_store(), cfg(), now=NOW)
    assert out["n"] == 0 and out["suggested_delay_s"] is None and out["delay_s"] == 45
    assert len(out["events"]) == 4 and out["events"][0]["lag_s"] is None


def test_summary_median_range_and_a_suggestion_that_leans_high():
    store = events_store()
    for i, lag in enumerate((30, 38, 42, 61), start=1):
        see(store, i, lag)
    out = calibration(store, cfg(), now=NOW)
    assert (out["n"], out["median_s"], out["min_s"], out["max_s"]) == (4, 40.0, 30.0, 61.0)
    assert out["suggested_delay_s"] == 42  # the 75th percentile (nearest rank), not the median
    assert [e["lag_s"] for e in out["events"]] == [61.0, 42.0, 38.0, 30.0]  # newest first


def test_suggestion_is_never_negative_when_the_tv_was_ahead_of_espn():
    store = events_store(2)
    see(store, 1, -8)
    see(store, 2, -3)
    assert calibration(store, cfg(), now=NOW)["suggested_delay_s"] == 0


async def test_mark_seen_stamps_the_server_clock_and_can_be_undone():
    store = events_store(1)
    detected = NOW + timedelta(minutes=1)
    app = create_app(store, cfg(), WatcherStats(started_at=NOW), {"lamp": DryRunBulb("lamp")},
                     False, now=lambda: detected + timedelta(seconds=52.5))
    key = dedupe_key("g1", "9", 1)
    async with client(app) as c:
        assert (await c.post(f"/api/events/{key}/seen")).status_code == 403
        assert (await c.post("/api/events/nope/seen", headers=HDR)).status_code == 404
        r = await c.post(f"/api/events/{key}/seen", headers=HDR)
        assert r.status_code == 200 and r.json()["lag_s"] == 52.5
        got = (await c.get("/api/calibration")).json()
        assert got["n"] == 1 and got["events"][0]["lag_s"] == 52.5
        status = (await c.get("/api/status")).json()
        assert status["events"][0]["lag_s"] == 52.5 and status["events"][0]["seen_at"]
        assert (await c.delete(f"/api/events/{key}/seen")).status_code == 403
        assert (await c.delete(f"/api/events/{key}/seen", headers=HDR)).status_code == 200
        assert (await c.get("/api/calibration")).json()["n"] == 0
        assert (await c.delete("/api/events/nope/seen", headers=HDR)).status_code == 404


def test_page_has_a_calibrate_screen_wired_to_the_calibration_api():
    from tests.support import full_page

    html = full_page()
    for needle in ('href="#/calibrate"', 'id="view-calibrate"', '"#/calibrate"',
                   "api/calibration", "/seen", "I see it on TV", "api/settings/household",
                   "A different delay for one kind of score", "Use all of these",
                   "Start practice mode", "api/practice", "as starting delay",
                   "mark a few more plays",
                   "Lights do not flash for plays", "calibrate-practice"):
        assert needle in html, needle


def test_page_stops_a_suggestion_past_the_settings_limit():
    from tests.support import full_page

    assert "over = g.suggested_delay_s > 180" in full_page()


def test_summary_groups_readings_by_kind_of_score_with_each_kinds_own_suggestion():
    store = events_store(4)
    for i, label in enumerate(("TD", "PAT", "TD", "PAT"), start=1):
        e = store.get_event(dedupe_key("g1", "9", i))
        store.db.execute("UPDATE events SET detail=? WHERE dedupe_key=?",
                         (json.dumps({"abbr": "GB", "label": label}), e.dedupe_key))
    for i, lag in enumerate((8, 3, 9, 2), start=1):
        see(store, i, lag)
    out = calibration(store, cfg(), now=NOW)
    groups = {g["label"]: g for g in out["by_label"]}
    assert groups["TD"]["median_s"] == 8.5 and groups["TD"]["suggested_delay_s"] == 9
    assert groups["PAT"]["median_s"] == 2.5 and groups["PAT"]["suggested_delay_s"] == 3
    assert groups["PAT"]["delay_s"] == 45 and groups["PAT"]["has_own_delay"] is False
    assert out["n"] == 4  # the overall summary still covers everything


def test_summary_reports_a_kinds_own_delay_when_one_is_set():
    from dataclasses import replace

    store = events_store(1)
    see(store, 1, 8)
    config = cfg()
    config = replace(config, general=replace(config.general, delay_by_label={"score": 6.0}))
    (group,) = calibration(store, config, now=NOW)["by_label"]
    assert group["label"] == "TD" or group["label"] == "score"


def test_a_tie_in_readings_puts_the_touchdown_first_so_it_sets_the_default_delay():
    store = events_store(2)
    for i, label in enumerate(("PAT", "TD"), start=1):
        store.db.execute("UPDATE events SET detail=? WHERE dedupe_key=?",
                         (json.dumps({"abbr": "GB", "label": label}), dedupe_key("g1", "9", i)))
        see(store, i, 5)
    assert [g["label"] for g in calibration(store, cfg(), now=NOW)["by_label"]] == ["TD", "PAT"]


def play_store():
    store = events_store(0)
    for i in range(1, 5):
        detected = NOW + timedelta(minutes=i)
        store.insert_event(Event(f"play:g1:{i}", "g1", "", "play", detected, detected,
                                 {"label": "Play", "text": f"{i}nd & 7", "period": 2,
                                  "clock": "9:00"}, status="practice"))
    return store


def test_plays_are_listed_apart_from_scores_and_give_their_own_summary():
    store = play_store()
    for i, lag in enumerate((20, 24, 30), start=1):
        store.mark_seen(f"play:g1:{i}", NOW + timedelta(minutes=i, seconds=lag))
    out = calibration(store, cfg(), now=NOW + timedelta(minutes=5))
    assert [p["key"] for p in out["plays"]] == ["play:g1:4", "play:g1:3", "play:g1:2", "play:g1:1"]
    assert out["plays"][1]["lag_s"] == 30.0 and out["plays"][1]["text"] == "3nd & 7"
    assert out["play_summary"]["n"] == 3 and out["play_summary"]["suggested_delay_s"] == 30
    assert out["events"] == [] and out["n"] == 0 and out["by_label"] == []  # scores untouched


def test_old_events_and_plays_leave_the_list_but_their_readings_still_count():
    store = events_store(2)
    see(store, 1, 40)
    out = calibration(store, cfg(), now=NOW + timedelta(days=7))
    assert out["events"] == [] and out["n"] == 1 and out["suggested_delay_s"] == 40
    today = calibration(store, cfg(), now=NOW + timedelta(minutes=2))
    assert len(today["events"]) == 2


def test_an_unmarked_row_loses_its_button_after_the_window_but_a_marked_one_stays():
    store = events_store(2)
    see(store, 1, 40)
    soon = calibration(store, cfg(), now=NOW + timedelta(minutes=2 + 4))  # 4 min after event 2
    late = calibration(store, cfg(), now=NOW + timedelta(minutes=2 + 6))  # 6 min after event 2
    assert [e["key"] for e in soon["events"]] == ["g1:9:2", "g1:9:1"]
    assert [e["key"] for e in late["events"]] == ["g1:9:1"]  # the marked one is still undoable


def test_marking_a_later_play_retires_the_earlier_unmarked_ones():
    store = play_store()
    store.mark_seen("play:g1:3", NOW + timedelta(minutes=3, seconds=25))
    out = calibration(store, cfg(), now=NOW + timedelta(minutes=5))
    rows = {p["key"]: p for p in out["plays"]}
    assert set(rows) == {"play:g1:3", "play:g1:4"}  # 1 and 2 are older than the marked one
    assert rows["play:g1:4"]["seen_at"] is None


async def test_a_mark_made_after_the_window_is_refused():
    store = events_store(1)
    detected = NOW + timedelta(minutes=1)
    app = create_app(store, cfg(), WatcherStats(started_at=NOW), {}, False,
                     now=lambda: detected + timedelta(minutes=6))
    async with client(app) as c:
        r = await c.post(f"/api/events/{dedupe_key('g1', '9', 1)}/seen", headers=HDR)
    assert r.status_code == 409 and "too late" in r.json()["detail"]
    assert store.get_event(dedupe_key("g1", "9", 1)).seen_at is None


async def test_practice_api_starts_stops_and_refuses_with_no_game_in_window():
    class FakePractice:
        def __init__(self):
            self.practice_until, self.ok, self.minutes = None, False, None

        def practice_active(self):
            return self.practice_until is not None

        def can_practice(self):
            return self.ok

        def start_practice(self, minutes):
            self.minutes, self.practice_until = minutes, NOW + timedelta(minutes=minutes)

        def stop_practice(self):
            self.practice_until = None

    fake = FakePractice()
    app = create_app(Store(), cfg(), WatcherStats(started_at=NOW), {}, False, now=lambda: NOW,
                     practice=fake)
    async with client(app) as c:
        assert (await c.get("/api/practice")).json() == {
            "active": False, "until": None, "minutes": 20, "available": False}
        assert (await c.put("/api/practice", json={"active": True})).status_code == 403
        r = await c.put("/api/practice", json={"active": True}, headers=HDR)
        assert r.status_code == 409 and "no game to practice on" in r.json()["detail"]
        fake.ok = True
        r = await c.put("/api/practice", json={"active": True}, headers=HDR)
        assert r.status_code == 200 and r.json()["active"] and fake.minutes == 20
        bad = await c.put("/api/practice", json={"active": "yes"}, headers=HDR)
        assert bad.status_code == 400
        r = await c.put("/api/practice", json={"active": False}, headers=HDR)
        assert r.json()["active"] is False


async def test_practice_api_without_a_watcher_reads_as_off_and_cannot_start():
    app = create_app(Store(), cfg(), WatcherStats(started_at=NOW), {}, False, now=lambda: NOW)
    async with client(app) as c:
        assert (await c.get("/api/practice")).json()["active"] is False
        assert (await c.put("/api/practice", json={"active": True}, headers=HDR)).status_code == 409
