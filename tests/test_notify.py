import asyncio
import json
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from app.config import ConfigError, HealthConfig, parse_config
from app.notify import HealthMonitor, SmtpNotifier, WebhookNotifier, make_notifier
from app.settings_service import config_to_toml
from app.watcher import WatcherStats
from tests.support import NOW, cfg


class Box:
    def __init__(self):
        self.sent = []

    async def send(self, subject, body):
        self.sent.append((subject, body))


class Clock:
    def __init__(self):
        self.t = NOW

    def __call__(self):
        return self.t

    def minutes(self, n):
        self.t += timedelta(minutes=n)


def monitor(stats, pings, health=None, box=None):
    clock, box = Clock(), box or Box()
    config = replace(cfg(), health=health or HealthConfig(name="Home", notify="webhook",
                                                           webhook_url="https://x.test/h"))

    async def ping():
        return pings

    m = HealthMonitor(lambda: config, stats, ping, clock, notifier=lambda h: box)
    return m, clock, box


def espn_down(clock_now=NOW):
    return WatcherStats(last_poll_at=clock_now, last_error="timed out")


async def test_espn_failure_waits_then_alerts_once_then_reports_recovery():
    stats = espn_down()
    m, clock, box = monitor(stats, {})
    await m.check()
    clock.minutes(4)
    stats.last_poll_at = clock()
    await m.check()
    assert box.sent == []  # not long enough yet
    clock.minutes(2)
    stats.last_poll_at = clock()
    await m.check()
    assert len(box.sent) == 1 and "ESPN is not answering" in box.sent[0][0]
    assert box.sent[0][0].startswith("Home:")
    clock.minutes(30)
    stats.last_poll_at = clock()
    await m.check()
    assert len(box.sent) == 1  # no repeat inside renotify_min
    stats.last_error = None
    await m.check()
    assert len(box.sent) == 2 and "back to normal" in box.sent[1][0]


async def test_reminder_after_renotify_min():
    stats = espn_down()
    m, clock, box = monitor(stats, {})
    await m.check()
    for _ in range(3):
        clock.minutes(60)
        stats.last_poll_at = clock()
        await m.check()
    assert len(box.sent) == 2  # at 60 min, then again after 120 more


async def test_stale_error_outside_a_game_is_not_a_problem():
    stats = WatcherStats(last_poll_at=NOW - timedelta(hours=10), last_error="timed out")
    m, clock, box = monitor(stats, {})
    clock.minutes(30)
    await m.check()
    clock.minutes(30)
    await m.check()
    assert box.sent == []


async def test_bulb_is_only_checked_while_a_game_is_watched():
    quiet = WatcherStats()
    m, clock, box = monitor(quiet, {"lamp": None})
    await m.check()
    clock.minutes(10)
    await m.check()
    assert box.sent == []
    live = WatcherStats(watching=["GB @ NE"])
    m, clock, box = monitor(live, {"lamp": None})
    await m.check()
    clock.minutes(6)
    await m.check()
    assert len(box.sent) == 1 and "bulb lamp is not answering" in box.sent[0][0]


async def test_a_short_blip_sends_nothing_even_on_recovery():
    stats = espn_down()
    m, clock, box = monitor(stats, {})
    await m.check()
    clock.minutes(1)
    stats.last_error = None
    await m.check()
    assert box.sent == []


async def test_broken_notifier_does_not_raise():
    class Broken:
        async def send(self, subject, body):
            raise RuntimeError("smtp down")

    stats = espn_down()
    m, clock, _ = monitor(stats, {}, box=Broken())
    await m.check()
    clock.minutes(6)
    stats.last_poll_at = clock()
    await m.check()  # must not raise


async def test_no_notifier_means_log_only(caplog):
    stats = espn_down()
    config = replace(cfg(), health=HealthConfig())
    clock = Clock()

    async def ping():
        return {}

    m = HealthMonitor(lambda: config, stats, ping, clock)
    assert make_notifier(config.health) is None
    await m.check()
    clock.minutes(6)
    stats.last_poll_at = clock()
    with caplog.at_level("WARNING"):
        await m.check()
    assert any("ESPN is not answering" in r.getMessage() for r in caplog.records)


async def test_webhook_posts_json():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(204)

    await WebhookNotifier("https://x.test/h", httpx.MockTransport(handler)).send("S", "B")
    assert json.loads(seen[0].content) == {"subject": "S", "body": "B", "text": "S\nB"}


async def test_webhook_error_status_raises():
    t = httpx.MockTransport(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await WebhookNotifier("https://x.test/h", t).send("S", "B")


async def test_smtp_builds_and_sends_a_message():
    log = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            log.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            log.append(("login", user, password))

        def send_message(self, msg):
            log.append(("send", msg["To"], msg["Subject"], msg.get_content().strip()))

    h = HealthConfig(notify="smtp", smtp_host="mail.test", smtp_user="u", smtp_password="p",
                     smtp_from="a@x.test", smtp_to="me@x.test")
    await SmtpNotifier(h, smtp_factory=FakeSmtp).send("Subj", "Body")
    assert log == [("connect", "mail.test", 587), ("login", "u", "p"),
                   ("send", "me@x.test", "Subj", "Body")]


def raw(**health):
    return {"general": {"dispatch_enabled": True, "db_path": "x.db"}, "health": health}


def test_config_requires_what_the_notifier_needs(tmp_path):
    with pytest.raises(ConfigError, match="webhook_url"):
        parse_config(raw(notify="webhook"), tmp_path)
    with pytest.raises(ConfigError, match="smtp_to"):
        parse_config(raw(notify="smtp", smtp_host="h", smtp_from="a@b.c"), tmp_path)
    with pytest.raises(ConfigError, match="notify"):
        parse_config(raw(notify="sms"), tmp_path)
    with pytest.raises(ConfigError, match="fail_after_min"):
        parse_config(raw(fail_after_min=0), tmp_path)
    ok = parse_config(raw(notify="smtp", smtp_host="h", smtp_from="a@b.c", smtp_to="d@e.f"),
                      tmp_path)
    assert ok.health.smtp_port == 587 and ok.health.name == "Gameday Lights"


def test_export_leaves_secrets_out_when_asked():
    h = HealthConfig(notify="smtp", smtp_host="h", smtp_from="a@b.c", smtp_to="d@e.f",
                     smtp_password="hunter2", webhook_url="https://x.test/tok",
                     heartbeat_url="https://hc.test/tok2")
    c = replace(cfg(), health=h)
    full = config_to_toml(c)
    assert all(s in full for s in ("hunter2", "tok2", "tok\""))
    safe = config_to_toml(c, include_secrets=False)
    assert not any(s in safe for s in ("hunter2", "tok2", "x.test/tok"))
    assert 'smtp_host = "h"' in safe


async def test_sleep_loop_is_cancellable():
    stats = WatcherStats()
    m, clock, box = monitor(stats, {})

    async def sleep(s):
        raise asyncio.CancelledError

    m._sleep = sleep
    with pytest.raises(asyncio.CancelledError):
        await m.run()
