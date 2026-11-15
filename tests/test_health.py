import asyncio
from dataclasses import replace

import httpx
import pytest

from app.config import ConfigError, HealthConfig, parse_config
from app.health import run_heartbeat
from app.settings_service import config_to_toml
from tests.support import cfg


def with_health(url, interval=300.0):
    return replace(cfg(), health=HealthConfig(url, interval))


async def run_rounds(config, handler, rounds):
    seen = []

    async def sleep(s):
        seen.append(s)
        if len(seen) >= rounds:
            raise asyncio.CancelledError

    transport = httpx.MockTransport(handler)
    with pytest.raises(asyncio.CancelledError):
        await run_heartbeat(lambda: config, transport, sleep)
    return seen


async def test_pings_the_url_every_interval():
    hits = []

    def handler(request):
        hits.append(str(request.url))
        return httpx.Response(200)

    sleeps = await run_rounds(with_health("https://hc.example/abc", 120), handler, 3)
    assert hits == ["https://hc.example/abc"] * 3 and sleeps == [120.0] * 3


async def test_no_url_makes_no_request():
    hits = []
    await run_rounds(with_health(None), lambda r: hits.append(r) or httpx.Response(200), 3)
    assert hits == []


async def test_failures_do_not_stop_it(caplog):
    answers = iter([500, 500, 200])
    hits = []

    def handler(request):
        hits.append(1)
        return httpx.Response(next(answers))

    with caplog.at_level("INFO"):
        await run_rounds(with_health("https://hc.example/x"), handler, 3)
    assert len(hits) == 3
    msgs = [r.getMessage() for r in caplog.records]
    assert sum("failing" in m for m in msgs) == 1 and any("back" in m for m in msgs)


async def test_network_error_is_survived():
    def handler(request):
        raise httpx.ConnectError("no route")

    seen = await run_rounds(with_health("https://hc.example/x"), handler, 2)
    assert len(seen) == 2


def raw(**health):
    return {"general": {"dispatch_enabled": True, "db_path": "x.db"}, "health": health}


def test_config_validation(tmp_path):
    ok = parse_config(
        raw(heartbeat_url=" https://hc.example/u ", heartbeat_interval_s=90), tmp_path)
    assert ok.health == HealthConfig("https://hc.example/u", 90.0)
    assert parse_config(raw(), tmp_path).health == HealthConfig()
    with pytest.raises(ConfigError, match="heartbeat_url"):
        parse_config(raw(heartbeat_url="ftp://x"), tmp_path)
    with pytest.raises(ConfigError, match="heartbeat_interval_s"):
        parse_config(raw(heartbeat_interval_s=30), tmp_path)


def test_export_keeps_the_url_unless_secrets_are_left_out():
    c = with_health("https://hc.example/secret-token")
    assert "secret-token" in config_to_toml(c)
    assert "secret-token" not in config_to_toml(c, include_secrets=False)
