import pytest

from app.bulbs.base import Pattern, Step
from app.bulbs.govee import (
    GoveeBulb,
    GoveeSnapshot,
    discover_govee,
    govee_brightness,
    snapshot_from_status,
)
from app.bulbs.wiz import BulbUnreachable

STATUS = {"onOff": 1, "brightness": 40, "color": {"r": 1, "g": 2, "b": 3}, "colorTemInKelvin": 0}


class FakeTransport:
    def __init__(self, status=STATUS, scans=(), fail=False):
        self.status, self.scans, self.fail = status, list(scans), fail
        self.sent: list[tuple] = []
        self.queries = 0

    async def send(self, ip, port, payload):
        if self.fail:
            raise OSError("network is unreachable")
        msg = payload["msg"]
        self.sent.append((ip, port, msg["cmd"], msg["data"]))

    async def query(self, ip, port, payload, expect, timeout):
        self.queries += 1
        if self.fail:
            raise OSError("network is unreachable")
        return self.status

    async def scan(self, wait_time):
        if self.fail:
            raise OSError("no route")
        return self.scans


def bulb(transport, **kw):
    async def no_sleep(_):
        return None

    return GoveeBulb("strip", "10.0.0.5", transport=transport, sleep=no_sleep, **kw)


def cmds(t):
    return [(c, d) for _, _, c, d in t.sent]


def test_brightness_maps_255_to_100():
    assert [govee_brightness(b) for b in (1, 128, 255)] == [1, 50, 100]


def test_snapshot_from_status_clamps_and_defaults():
    assert snapshot_from_status(STATUS) == GoveeSnapshot(True, (1, 2, 3), 40, 0)
    assert snapshot_from_status({"onOff": 0, "brightness": 0}).brightness == 1


async def test_set_color_turns_on_once_and_sends_brightness_only_on_change():
    t = FakeTransport()
    b = bulb(t)
    await b.set_color((0, 255, 0), 255)
    await b.set_color((255, 255, 255), 255)
    assert cmds(t) == [
        ("turn", {"value": 1}),
        ("brightness", {"value": 100}),
        ("colorwc", {"color": {"r": 0, "g": 255, "b": 0}, "colorTemInKelvin": 0}),
        ("colorwc", {"color": {"r": 255, "g": 255, "b": 255}, "colorTemInKelvin": 0}),
    ]
    assert {(ip, port) for ip, port, _, _ in t.sent} == {("10.0.0.5", 4003)}
    await b.set_color((0, 255, 0), 128)
    assert cmds(t)[-2] == ("brightness", {"value": 50})


async def test_snapshot_then_restore_color():
    t = FakeTransport()
    b = bulb(t)
    snap = await b.snapshot()
    await b.set_color((0, 255, 0), 255)
    t.sent.clear()
    await b.restore(snap)
    assert cmds(t) == [
        ("colorwc", {"color": {"r": 1, "g": 2, "b": 3}, "colorTemInKelvin": 0}),
        ("brightness", {"value": 40}),
    ]


async def test_restore_when_it_was_off_turns_it_off():
    t = FakeTransport(status={"onOff": 0, "brightness": 40, "color": {}, "colorTemInKelvin": 0})
    b = bulb(t)
    snap = await b.snapshot()
    await b.set_color((0, 255, 0))
    t.sent.clear()
    await b.restore(snap)
    assert cmds(t) == [("turn", {"value": 0})]


async def test_restore_color_temperature():
    t = FakeTransport(status={**STATUS, "colorTemInKelvin": 3000})
    b = bulb(t)
    snap = await b.snapshot()
    t.sent.clear()
    await b.restore(snap)
    assert cmds(t)[0] == (
        "colorwc", {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": 3000}
    )


async def test_flash_sends_every_step():
    t = FakeTransport()
    b = bulb(t)
    await b.flash(Pattern((Step((0, 255, 0), 0.5), Step((255, 215, 0), 0.5))))
    assert [c for c in cmds(t) if c[0] == "colorwc"] == [
        ("colorwc", {"color": {"r": 0, "g": 255, "b": 0}, "colorTemInKelvin": 0}),
        ("colorwc", {"color": {"r": 255, "g": 215, "b": 0}, "colorTemInKelvin": 0}),
    ]


async def test_ping_returns_seconds_and_sends_no_commands():
    t = FakeTransport()
    assert await bulb(t).ping() is not None
    assert t.sent == []


async def test_no_answer_retries_once_then_snapshot_raises_and_ping_is_none():
    t = FakeTransport(status=None)
    b = bulb(t)
    with pytest.raises(BulbUnreachable, match="LAN Control"):
        await b.snapshot()
    assert t.queries == 2
    assert await b.ping() is None


async def test_network_errors_become_bulb_unreachable():
    b = bulb(FakeTransport(fail=True))
    with pytest.raises(BulbUnreachable, match="network is unreachable"):
        await b.set_color((0, 255, 0))
    assert await b.ping() is None


async def test_discover_dedupes_by_device_and_sorts_by_ip():
    scans = [
        {"ip": "192.168.0.27", "device": "0D:A8:DE:99:C4:C6:47:5F"},
        {"ip": "192.168.0.9", "device": "AA:BB:CC:DD:EE:FF:00:11"},
        {"ip": "192.168.0.27", "device": "0D:A8:DE:99:C4:C6:47:5F"},
    ]
    found = await discover_govee(transport=FakeTransport(scans=scans))
    assert found == [
        {"ip": "192.168.0.9", "mac": "aabbccddeeff0011"},
        {"ip": "192.168.0.27", "mac": "0da8de99c4c6475f"},
    ]


async def test_discover_failure_is_bulb_unreachable():
    with pytest.raises(BulbUnreachable, match="discovery failed: no route"):
        await discover_govee(transport=FakeTransport(fail=True))


def test_govee_capabilities_follow_segment_count():
    t = FakeTransport()
    assert bulb(t).capabilities.kinds == {"pulse"}
    strip = bulb(t, segments=20)
    assert strip.capabilities.segments == 20
    assert "chase" in strip.capabilities.kinds


def test_razer_packet_matches_known_enable_string():
    import base64

    from app.bulbs.govee import razer_packet

    assert base64.b64encode(razer_packet(0xB1, [1])) == b"uwABsQEK"
    assert base64.b64encode(razer_packet(0xB1, [0])) == b"uwABsQAL"


async def test_play_segments_enables_streams_frames_and_disables():
    import base64

    from app.bulbs.base import SegmentFrame, SegmentPattern

    t = FakeTransport()
    strip = bulb(t, segments=2)
    red, green = (255, 0, 0), (0, 255, 0)
    frames = (SegmentFrame((red, green), 0.6), SegmentFrame((green, red), 0.6))
    await strip.play(SegmentPattern(frames, brightness=128))
    packets = [base64.b64decode(d["pt"]) for c, d in cmds(t) if c == "razer"]
    assert packets[0][3:5] == bytes([0xB1, 1])  # enable
    assert packets[1][3:5] == bytes([0xB0, 0])  # LED data, discrete
    assert packets[1][5] == 2  # two segments
    assert packets[-1][3:5] == bytes([0xB1, 0])  # disabled again
    assert ("brightness", {"value": 50}) in cmds(t)


async def test_play_segments_rejects_wrong_segment_count():
    from app.bulbs.base import PatternError, SegmentFrame, SegmentPattern

    strip = bulb(FakeTransport(), segments=3)
    with pytest.raises(PatternError):
        await strip.play(SegmentPattern((SegmentFrame(((0, 0, 0), (1, 1, 1)), 0.6),)))


async def test_play_segments_disables_streaming_when_a_frame_fails():
    import base64

    from app.bulbs.base import SegmentFrame, SegmentPattern

    class Flaky(FakeTransport):
        async def send(self, ip, port, payload):
            msg = payload["msg"]
            if msg["cmd"] == "razer" and base64.b64decode(msg["data"]["pt"])[3] == 0xB0:
                raise OSError("boom")
            await super().send(ip, port, payload)

    t = Flaky()
    strip = bulb(t, segments=1)
    with pytest.raises(BulbUnreachable):
        await strip.play(SegmentPattern((SegmentFrame(((1, 2, 3),), 0.6),)))
    last = [base64.b64decode(d["pt"]) for c, d in cmds(t) if c == "razer"][-1]
    assert last[3:5] == bytes([0xB1, 0])
