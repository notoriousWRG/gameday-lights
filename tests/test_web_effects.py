

from tests.support import (
    HDR,
    Recorder,
    client,
    full_page,
    make,
    make_matrix,
    page_text,
)


async def test_page_has_the_effects_screen_with_a_test_button_on_the_pulse_path():
    async with client(make()) as c:
        html = await page_text(c)
    for needle in ('id="tab-effects"', 'href="#/effects"', 'id="view-effects"',
                   'section: "effects"', "effects.score.pulses", "FLASH_CAP", "Use team colors",
                   "Save & test", "pulse(testBulb)",
                   "api/bulbs/${encodeURIComponent(name)}/pulse"):
        assert needle in html, needle
    assert "innerHTML" not in html


async def test_matrix_lists_each_team_bulb_with_kinds_and_where_settings_come_from():
    app = make_matrix({"lamp": Recorder("lamp"), "strip": Recorder("strip")})
    async with client(app) as c:
        r = await c.get("/api/effects/matrix")
    cells = {x["bulb"]: x for x in r.json()["cells"]}
    lamp, strip = cells["lamp"], cells["strip"]
    assert lamp["kinds"] == ["pulse"] and strip["kinds"] == ["chase", "pulse"]
    assert (lamp["kind"], lamp["kind_from"]) == ("pulse", "default")
    assert lamp["params"]["duration_s"] == {"value": 4.0, "from": "team"}
    assert lamp["params"]["pulses"] == {"value": 5, "from": "default"}
    assert (strip["kind"], strip["kind_from"]) == ("chase", "team x fixture")
    assert strip["params"]["chunk"] == {"value": 5, "from": "team x fixture"}
    assert strip["params"]["speed"] == {"value": 4.0, "from": "built-in"}
    assert strip["color"] == {"value": "#00ff00", "from": "team"}
    assert strip["alt_color"] == {"value": "#ff8c00", "from": "team x fixture"}
    assert lamp["alt_color"] == {"value": None, "from": None}  # falls back to ESPN at play time


async def test_matrix_test_plays_the_same_pattern_an_event_would_and_restores():
    strip = Recorder("strip")
    app = make_matrix({"lamp": Recorder("lamp"), "strip": strip})
    async with client(app) as c:
        r = await c.post("/api/effects/test", headers=HDR,
                         json={"league": "nfl", "id": "9", "bulb": "strip"})
    assert r.status_code == 200
    assert [x[0] for x in strip.calls] == ["snapshot", "play_segments", "restore"]
    assert strip.calls[1][2] == 20  # segments


async def test_matrix_test_needs_header_and_rejects_unknown_team_bulb_pairs():
    app = make_matrix({"lamp": Recorder("lamp"), "strip": Recorder("strip")})
    body = {"league": "nfl", "id": "9", "bulb": "strip"}
    async with client(app) as c:
        assert (await c.post("/api/effects/test", json=body)).status_code == 403
        assert (await c.post("/api/effects/test", headers=HDR, json={})).status_code == 400
        other = {"league": "nfl", "id": "1", "bulb": "strip"}
        assert (await c.post("/api/effects/test", headers=HDR, json=other)).status_code == 404


async def test_matrix_also_lists_every_bulb_with_its_kinds_for_the_default_rows():
    app = make_matrix({"lamp": Recorder("lamp"), "strip": Recorder("strip")})
    async with client(app) as c:
        bulbs = {b["name"]: b for b in (await c.get("/api/effects/matrix")).json()["bulbs"]}
    assert bulbs["lamp"]["kinds"] == ["pulse"]
    assert bulbs["strip"]["kinds"] == ["chase", "pulse"] and bulbs["strip"]["segments"] == 20


def test_page_has_bulb_defaults_team_effect_and_collapsed_cells():
    html = full_page()
    for needle in ("Bulb defaults", 'id="fixtures-body"', "function layerFields(",
                   "function mxTeamRow(", '"Customize"', "Same as the level above"):
        assert needle in html, needle
