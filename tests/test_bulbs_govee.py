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
        {"ip": "192.168.0.9", "mac": "aabbccddeeff0011", "sku": None, "segments": 1},
        {"ip": "192.168.0.27", "mac": "0da8de99c4c6475f", "sku": None, "segments": 1},
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


async def test_set_state_color_white_brightness_and_off():
    from app.bulbs.base import BulbState

    t = FakeTransport()
    b = bulb(t)
    await b.set_state(BulbState(color=(0, 255, 0), brightness=255))
    await b.set_state(BulbState(color_temp_k=2700))
    await b.set_state(BulbState(on=False))
    sent = cmds(t)
    assert ("turn", {"value": 1}) in sent
    assert ("brightness", {"value": 100}) in sent
    assert ("colorwc", {"color": {"r": 0, "g": 255, "b": 0}, "colorTemInKelvin": 0}) in sent
    assert ("colorwc", {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": 2700}) in sent
    assert sent[-1] == ("turn", {"value": 0})


async def test_current_state_scales_brightness_and_tells_color_from_white():
    t = FakeTransport(status={"onOff": 1, "brightness": 40, "color": {"r": 1, "g": 2, "b": 3},
                              "colorTemInKelvin": 0})
    got = await bulb(t).current_state()
    assert (got.on, got.color, got.color_temp_k, got.brightness) == (True, (1, 2, 3), None, 102)
    t = FakeTransport(status={"onOff": 1, "brightness": 100, "color": {"r": 0, "g": 0, "b": 0},
                              "colorTemInKelvin": 3000})
    got = await bulb(t).current_state()
    assert got.color is None and got.color_temp_k == 3000 and got.brightness == 255


def test_segments_for_sku_knows_verified_models_only():
    from app.bulbs.govee import segments_for_sku

    assert segments_for_sku("H616D") == 20 and segments_for_sku("h616d") == 20
    assert segments_for_sku("H6199") == 1 and segments_for_sku(None) == 1


async def test_discovery_reports_the_model_and_its_segments():
    scans = [{"ip": "192.168.0.27", "device": "0D:A8:DE:99:C4:C6:47:5F", "sku": "H616D"}]
    found = await discover_govee(transport=FakeTransport(scans=scans))
    assert found == [{"ip": "192.168.0.27", "mac": "0da8de99c4c6475f", "sku": "H616D",
                      "segments": 20}]


class ReadbackTransport(FakeTransport):
    """devStatus answers come from a list, one per read (the last one repeats)."""

    def __init__(self, reads):
        super().__init__(status=reads[-1])
        self.reads = list(reads)

    async def query(self, ip, port, payload, expect, timeout):
        self.queries += 1
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]


DIM = {"onOff": 1, "brightness": 1, "color": {"r": 255, "g": 0, "b": 0}, "colorTemInKelvin": 0}
BRIGHT = {**DIM, "brightness": 100}


async def test_restore_that_did_not_take_is_repeated_until_it_does():
    t = ReadbackTransport([BRIGHT, BRIGHT, DIM])  # reads back bright twice, then dim
    strip = bulb(t)
    await strip.restore(snapshot_from_status(DIM))
    brightness_sends = [d for c, d in cmds(t) if c == "brightness"]
    assert brightness_sends == [{"value": 1}] * 3  # re-sent, even though the cache said "done"
    assert t.queries == 3


async def test_restore_that_took_is_not_repeated():
    t = ReadbackTransport([DIM])
    await bulb(t).restore(snapshot_from_status(DIM))
    assert t.queries == 1 and len([1 for c, _ in cmds(t) if c == "colorwc"]) == 1


async def test_restore_gives_up_loudly_after_three_tries(caplog):
    t = ReadbackTransport([BRIGHT])
    await bulb(t).restore(snapshot_from_status(DIM))
    assert t.queries == 3 and "could not confirm the restore" in caplog.text


async def test_off_snapshot_is_verified_too():
    t = ReadbackTransport([{**DIM, "onOff": 1}, {**DIM, "onOff": 0}])
    await bulb(t).restore(snapshot_from_status({**DIM, "onOff": 0}))
    assert [d for c, d in cmds(t) if c == "turn"] == [{"value": 0}, {"value": 0}]


async def test_streaming_waits_after_leaving_the_mode_before_anything_else_is_sent():
    from app.bulbs.base import SegmentFrame, SegmentPattern

    slept = []

    async def sleep(s):
        slept.append(s)

    t = FakeTransport()
    strip = GoveeBulb("strip", "10.0.0.5", transport=t, sleep=sleep, segments=1)
    await strip.play(SegmentPattern((SegmentFrame(((1, 2, 3),), 0.6),)))
    assert slept[-1] == 0.3  # the settle wait comes after the disable packet, which is last sent
    assert t.sent[-1][2] == "razer"


MOVED_SCAN = [{"ip": "10.0.0.9", "device": "0D:A8:DE:99:C4:C6:47:5F"}]


class MovingTransport(FakeTransport):
    """Answers status only at `at`; scans find the strip there."""

    def __init__(self, at="10.0.0.9", scans=MOVED_SCAN):
        super().__init__(scans=scans)
        self.at = at
        self.scanned = 0

    async def query(self, ip, port, payload, expect, timeout):
        self.queries += 1
        return self.status if ip == self.at else None

    async def scan(self, wait_time):
        self.scanned += 1
        return self.scans


def moved_bulb(t, clock=lambda: 0.0, mac="0da8de99c4c6475f"):
    async def no_sleep(_):
        return None

    return GoveeBulb("strip", "10.0.0.5", mac=mac, transport=t, sleep=no_sleep, clock=clock)


async def test_strip_that_moved_is_found_again_by_device_id():
    t = MovingTransport()
    b = moved_bulb(t)
    snap = await b.snapshot()
    assert snap.brightness == 40
    assert b.ip == "10.0.0.9"
    await b.set_color((0, 255, 0))
    assert {ip for ip, *_ in t.sent} == {"10.0.0.9"}


async def test_ping_never_rescans():
    t = MovingTransport()
    b = moved_bulb(t)
    assert await b.ping() is None
    assert t.scanned == 0 and b.ip == "10.0.0.5"


async def test_strip_without_a_device_id_is_not_searched_for():
    t = MovingTransport()
    b = moved_bulb(t, mac=None)
    with pytest.raises(BulbUnreachable):
        await b.snapshot()
    assert t.scanned == 0


async def test_gone_strip_scans_once_per_window(caplog):
    t = MovingTransport(scans=[])
    now = [0.0]
    b = moved_bulb(t, clock=lambda: now[0])
    for _ in range(2):
        with pytest.raises(BulbUnreachable):
            await b.snapshot()
    assert t.scanned == 1
    now[0] = 31.0
    with pytest.raises(BulbUnreachable):
        await b.snapshot()
    assert t.scanned == 2


async def test_strip_found_at_the_same_ip_is_not_treated_as_moved():
    t = MovingTransport(at="nowhere", scans=[{"ip": "10.0.0.5", "device": "0DA8DE99C4C6475F"}])
    b = moved_bulb(t)
    with pytest.raises(BulbUnreachable):
        await b.snapshot()
    assert b.ip == "10.0.0.5"
