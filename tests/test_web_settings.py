import copy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app import settings
from app.bulbs.base import DryRunBulb
from app.config import load_config
from app.settings_service import SettingsService
from app.store import Store
from app.watcher import WatcherStats
from app.web.status import create_app

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
H = {"X-Gameday": "1"}


def make():
    cfg = load_config(ROOT / "config.example.toml")
    store = Store()
    svc = SettingsService(store, settings.machine_raw_from_config(cfg), ROOT, now=lambda: NOW)
    svc.seed(cfg)
    svc.load()
    bulbs = {b.name: DryRunBulb(b.name) for b in cfg.bulbs}
    app = create_app(store, lambda: svc.config, WatcherStats(started_at=NOW), bulbs, False,
                     now=lambda: NOW, settings=svc)
    return app, svc


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def put(c, section, value, rev, headers=None):
    h = {**H, "If-Match": str(rev)} if headers is None else headers
    return await c.put(f"/api/settings/{section}", json={"value": value}, headers=h)


async def current(c, section):
    return (await c.get("/api/settings")).json()["sections"][section]


async def test_get_lists_every_section_with_revisions_and_read_only_machine_settings():
    app, svc = make()
    async with client(app) as c:
        body = (await c.get("/api/settings")).json()
    assert set(body["sections"]) == set(settings.SECTIONS)
    assert all(s["revision"] == 1 for s in body["sections"].values())
    assert body["sections"]["household"]["value"] == {"delay_s": 45.0}
    assert body["machine"]["dispatch_enabled"] is True and body["machine"]["editable"] is False
    assert body["machine"]["web"]["port"] == 8787
    assert "dispatch_enabled" not in str(body["sections"])  # not an editable setting


async def test_save_applies_live_and_bumps_the_revision():
    app, svc = make()
    async with client(app) as c:
        assert (await c.get("/api/status")).json()["delay_s"] == 45
        r = await put(c, "household", {"delay_s": 30}, 1)
        assert r.status_code == 200
        assert r.json() == {"revision": 2, "value": {"delay_s": 30.0}, "applied": True}
        assert (await c.get("/api/status")).json()["delay_s"] == 30  # live, no restart
        assert (await current(c, "household"))["revision"] == 2
    assert svc.config.general.delay_s == 30


async def test_every_write_refusal():
    app, svc = make()
    async with client(app) as c:
        ok = {"delay_s": 30}
        assert (await put(c, "household", ok, 1, headers={"If-Match": "1"})).status_code == 403
        assert (await put(c, "general", ok, 1)).status_code == 404  # machine: not a section
        assert (await put(c, "nope", ok, 1)).status_code == 404
        assert (await put(c, "household", ok, 1, headers=H)).status_code == 428  # no If-Match
        assert (await put(c, "household", ok, "abc")).status_code == 400
        raw = await c.put("/api/settings/household", content=b"{not json",
                          headers={**H, "If-Match": "1"})
        assert raw.status_code == 400
        for bad in ([1], {"no_value": 1}, "text"):
            r = await c.put("/api/settings/household", json=bad, headers={**H, "If-Match": "1"})
            assert r.status_code == 400
        assert (await current(c, "household"))["revision"] == 1  # nothing was written


async def test_if_match_accepts_quoted_and_weak_forms():
    app, svc = make()
    async with client(app) as c:
        r = await c.put("/api/settings/household", json={"value": {"delay_s": 31}},
                        headers={**H, "If-Match": 'W/"1"'})
        assert r.status_code == 200
        r = await c.put("/api/settings/household", json={"value": {"delay_s": 32}},
                        headers={**H, "If-Match": '"2"'})
        assert r.status_code == 200 and r.json()["revision"] == 3


@pytest.mark.parametrize("section,mutate,where,text", [
    ("advanced", lambda v: v.update(poll_live_s=5), ("advanced", "poll_live_s"), "must be >= 10"),
    ("advanced", lambda v: v.update(pulse_cooldown_s=0), ("advanced", "pulse_cooldown_s"), ">= 1"),
    ("household", lambda v: v.update(delay_s=-1), ("household", "delay_s"), "must be >= 0"),
    ("household", lambda v: v.update(dispatch_enabled=True), ("household", "household"),
     "unknown field 'dispatch_enabled'"),
    ("advanced", lambda v: v.update(db_path="/tmp/x"), ("advanced", "advanced"),
     "unknown field 'db_path'"),
    ("effects", lambda v: v["score"].update(pulses=10), ("effects", "effects.score"), "cap"),
])
async def test_invalid_edits_get_422_naming_the_editor_field_and_change_nothing(
    section, mutate, where, text
):
    app, svc = make()
    async with client(app) as c:
        value = copy.deepcopy((await current(c, section))["value"])
        mutate(value)
        r = await put(c, section, value, 1)
        assert r.status_code == 422
        (err,) = r.json()["errors"]
        assert (err["section"], err["path"]) == where and text in err["message"], err
        assert (await current(c, section))["revision"] == 1


async def test_a_team_cannot_reference_a_bulb_that_does_not_exist():
    app, svc = make()
    async with client(app) as c:
        teams = (await current(c, "teams"))["value"]
        teams[0]["bulbs"] = ["ghost"]
        r = await put(c, "teams", teams, 1)
        assert r.status_code == 422
        assert r.json()["errors"][0] == {"section": "teams", "path": "teams[0].bulbs",
                                         "message": "unknown bulb 'ghost'"}


async def test_removing_a_bulb_a_team_uses_is_refused_and_points_at_the_team():
    app, svc = make()
    async with client(app) as c:
        r = await put(c, "bulbs", [], 1)
        assert r.status_code == 422
        err = r.json()["errors"][0]
        assert err["section"] == "teams" and "unknown bulb" in err["message"]  # fix the team first


async def test_second_editor_with_a_stale_revision_gets_409_and_the_current_value():
    app, svc = make()
    async with client(app) as phone_a, client(app) as phone_b:
        assert (await put(phone_a, "household", {"delay_s": 30}, 1)).status_code == 200
        r = await put(phone_b, "household", {"delay_s": 99}, 1)  # B still holds revision 1
        assert r.status_code == 409
        body = r.json()
        assert body["current_revision"] == 2 and body["value"] == {"delay_s": 30.0}
        assert svc.config.general.delay_s == 30  # A's save stands
        # B re-reads, edits again with the new revision, and succeeds
        assert (await put(phone_b, "household", {"delay_s": 99}, 2)).status_code == 200


async def test_following_a_team_through_the_api_shows_up_in_status_immediately():
    app, svc = make()
    async with client(app) as c:
        teams = (await current(c, "teams"))["value"]
        teams.append({"league": "nfl", "id": "17", "abbr": "NE", "bulbs": ["living-room"],
                      "color": "#1f4fd8", "alt_color": None})
        assert (await put(c, "teams", teams, 1)).status_code == 200
        status = (await c.get("/api/status")).json()
    assert [t["key"] for t in status["teams"]] == ["nfl:GB", "nfl:NE"]
    assert status["teams"][1]["color"] == "#1f4fd8"


async def test_signing_keys_never_leave_the_server_in_any_response():
    app, svc = make()
    async with client(app) as c:
        bulbs = (await current(c, "bulbs"))["value"]
        bulbs[0]["signing_key"] = "s3cret-key"
        r = await put(c, "bulbs", bulbs, 1)
        assert r.status_code == 200 and "s3cret-key" not in r.text
        assert r.json()["value"][0]["has_signing_key"] is True
        for path in ("/api/settings", "/api/settings/history", "/api/status"):
            assert "s3cret-key" not in (await c.get(path)).text, path
        # the browser sends back what it was given (a flag, no key): the stored key survives
        shown = (await current(c, "bulbs"))
        shown["value"][0]["port"] = 38900
        assert (await put(c, "bulbs", shown["value"], shown["revision"])).status_code == 200
        # a 422 or 409 must not echo it either
        bad = copy.deepcopy(shown["value"])
        bad[0]["ip"] = ""
        r = await put(c, "bulbs", bad, 99)
        assert "s3cret-key" not in r.text
    assert svc.config.bulbs[0].signing_key == "s3cret-key" and svc.config.bulbs[0].port == 38900


async def test_history_is_newest_first_filterable_and_records_the_source():
    app, svc = make()
    async with client(app) as c:
        await put(c, "household", {"delay_s": 30}, 1)
        await put(c, "advanced", {**(await current(c, "advanced"))["value"],
                                  "poll_live_s": 12}, 1)
        hist = (await c.get("/api/settings/history?limit=3")).json()
        assert [(h["section"], h["revision"], h["source"]) for h in hist] == [
            ("advanced", 2, "ui"), ("household", 2, "ui"), ("advanced", 1, "config.toml")]
        assert hist[1]["value"] == {"delay_s": 30.0}
        only = (await c.get("/api/settings/history?section=household")).json()
        assert [h["revision"] for h in only] == [2, 1]
        assert len((await c.get("/api/settings/history?limit=0")).json()) == 1  # clamped, no error


async def test_a_no_op_save_changes_nothing():
    app, svc = make()
    async with client(app) as c:
        r = await put(c, "household", {"delay_s": 45}, 1)
        assert r.status_code == 200 and r.json()["revision"] == 1
        assert len((await c.get("/api/settings/history")).json()) == len(settings.SECTIONS)


async def test_settings_routes_do_not_exist_without_a_settings_service():
    from tests.test_web_status import make as make_status

    async with client(make_status()) as c:
        assert (await c.get("/api/settings")).status_code == 404
        assert (await put(c, "household", {"delay_s": 30}, 1)).status_code == 404


# --- team search ----------------------------------------------------------------------------

class FakeEspn:
    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    async def teams(self, league):
        from app.espn.client import EspnError

        self.calls.append(league)
        if self.fail:
            raise EspnError("down for the weekend")
        import json

        return json.loads((ROOT / "tests" / "fixtures" / "teams" / f"{league}.json").read_text())


def make_with_espn(fail=False):
    cfg = load_config(ROOT / "config.example.toml")
    store = Store()
    svc = SettingsService(store, settings.machine_raw_from_config(cfg), ROOT, now=lambda: NOW)
    svc.seed(cfg)
    svc.load()
    espn = FakeEspn(fail)
    app = create_app(store, lambda: svc.config, WatcherStats(started_at=NOW), {}, False,
                     now=lambda: NOW, settings=svc, espn=espn)
    return app, svc, espn


async def search(c, league="nfl", q=""):
    return await c.get("/api/teams/search", params={"league": league, "q": q})


async def test_leagues_lists_the_supported_leagues():
    app, _, _ = make_with_espn()
    async with client(app) as c:
        assert (await c.get("/api/leagues")).json() == [
            {"key": "nfl", "label": "NFL"}, {"key": "nhl", "label": "NHL"}]


async def test_search_matches_names_abbreviations_and_multiple_words_case_insensitively():
    app, _, _ = make_with_espn()
    async with client(app) as c:
        assert len((await search(c)).json()) == 32  # empty query: everything
        assert [t["abbr"] for t in (await search(c, q="green bay")).json()] == ["GB"]
        assert [t["abbr"] for t in (await search(c, q="PACK")).json()] == ["GB"]
        assert [t["abbr"] for t in (await search(c, q="gb")).json()] == ["GB"]
        assert [t["abbr"] for t in (await search(c, q="  new   england ")).json()] == ["NE"]
        assert (await search(c, q="zzzz")).json() == []
        new = {t["abbr"] for t in (await search(c, q="new")).json()}
        assert {"NE", "NO", "NYG", "NYJ"} <= new  # several New ... teams


async def test_search_result_carries_what_the_follow_form_needs():
    app, _, _ = make_with_espn()
    async with client(app) as c:
        (gb,) = (await search(c, q="green bay")).json()
    assert gb == {"id": "9", "abbr": "GB", "name": "Green Bay Packers", "short_name": "Packers",
                  "color": "#204e32", "alt_color": "#ffb612", "league": "nfl", "followed": True}


async def test_search_marks_followed_teams_per_league():
    app, svc, _ = make_with_espn()
    teams = svc.sections()["teams"][1]
    teams.append({"league": "nhl", "id": "16", "abbr": "PIT", "bulbs": ["living-room"],
                  "color": None, "alt_color": None})
    svc.update("teams", teams, 1)
    async with client(app) as c:
        nfl_pit = (await search(c, "nfl", "pittsburgh")).json()
        nhl_pit = (await search(c, "nhl", "pittsburgh")).json()
        nhl_gb = (await search(c, "nhl", "")).json()
    assert [(t["name"], t["followed"]) for t in nfl_pit] == [("Pittsburgh Steelers", False)]
    assert [(t["name"], t["followed"]) for t in nhl_pit] == [("Pittsburgh Penguins", True)]
    assert not any(t["followed"] for t in nhl_gb if t["abbr"] == "GB")  # GB follows only in the NFL


async def test_search_follows_settings_changes_without_a_restart():
    app, svc, _ = make_with_espn()
    async with client(app) as c:
        assert (await search(c, q="patriots")).json()[0]["followed"] is False
        teams = svc.sections()["teams"][1]
        teams.append({"league": "nfl", "id": "17", "abbr": "NE", "bulbs": ["living-room"],
                      "color": None, "alt_color": None})
        svc.update("teams", teams, 1)
        assert (await search(c, q="patriots")).json()[0]["followed"] is True


async def test_search_errors():
    app, _, espn = make_with_espn()
    async with client(app) as c:
        assert (await search(c, "curling")).status_code == 400
        assert espn.calls == []  # the league is checked before ESPN is asked
        assert (await c.get("/api/teams/search")).status_code == 422  # league is required
    app, _, _ = make_with_espn(fail=True)
    async with client(app) as c:
        r = await search(c)
        assert r.status_code == 502 and "down for the weekend" in r.json()["detail"]


async def test_search_routes_do_not_exist_without_an_espn_client():
    app, _ = make()
    async with client(app) as c:
        assert (await c.get("/api/leagues")).status_code == 404
        assert (await c.get("/api/teams/search?league=nfl")).status_code == 404
