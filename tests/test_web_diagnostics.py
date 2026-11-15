from dataclasses import replace

import pytest

from app.bulbs.base import DryRunBulb
from app.config import BulbConfig
from app.main import build_parser
from app.store import Store
from app.watcher import WatcherStats
from app.web.status import create_app
from tests.support import NOW, client, make
from tests.support import cfg as base_cfg


async def test_diagnostics_shape_and_bundle():
    async with client(make()) as c:
        d = (await c.get("/api/diagnostics")).json()
    assert d["mode"] == "live" and d["teams"] == ["GB"] and d["uptime_s"] == 3600
    assert d["bulbs"] == [{"name": "lamp", "kind": "wiz", "ip": "10.0.0.5",
                           "reachable": True, "ping_ms": 0}]
    assert d["watcher"]["polls"] == 5 and d["last_event"]["label"] == "TD"
    for line in ("bulb lamp (wiz 10.0.0.5): 0 ms", "teams: GB", "last event: GB @ NE TD fired"):
        assert line in d["bundle"]
    assert d["now"] == NOW.isoformat()


async def test_diagnostics_has_no_secret_value():
    secret = "sup3r-secret-signing-key"
    config = base_cfg()
    config = replace(config, bulbs=(BulbConfig("lamp", "10.0.0.5", signing_key=secret),))
    app = create_app(Store(), config, WatcherStats(started_at=NOW), {"lamp": DryRunBulb("lamp")},
                     False, now=lambda: NOW)
    async with client(app) as c:
        r = await c.get("/api/diagnostics")
    assert secret not in r.text


async def test_diagnostics_says_whether_the_heartbeat_is_set_but_not_the_url():
    from app.config import HealthConfig

    config = replace(base_cfg(), health=HealthConfig("https://hc.example/private-token"))
    app = create_app(Store(), config, WatcherStats(started_at=NOW), {}, False, now=lambda: NOW)
    async with client(app) as c:
        r = await c.get("/api/diagnostics")
    assert r.json()["heartbeat_set"] is True and "private-token" not in r.text


async def test_diagnostics_is_read_only():
    async with client(make()) as c:
        assert (await c.post("/api/diagnostics", headers={"X-Gameday": "1"})).status_code == 405


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.startswith("gameday-lights ")
