import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_govee_segments.py"
spec = importlib.util.spec_from_file_location("probe_govee_segments", SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_govee_segments"] = probe
spec.loader.exec_module(probe)

STATUS = {"onOff": 1, "brightness": 40, "color": {"r": 9, "g": 8, "b": 7}, "colorTemInKelvin": 0}


class FakeTransport:
    def __init__(self):
        self.sent = []

    async def send(self, ip, port, payload):
        self.sent.append(payload["msg"])

    async def query(self, ip, port, payload, expect, timeout):
        return STATUS

    async def scan(self, wait_time):
        return []


def test_enable_packet_matches_known_base64():
    pkt = probe.build_packet(probe.ENABLE, [1])
    assert base64.b64encode(pkt) == b"uwABsQEK"
    assert base64.b64encode(probe.build_packet(probe.ENABLE, [0])) == b"uwABsQAL"


def test_led_frame_layout_and_checksum():
    pkt = probe.led_frame([(1, 2, 3), (4, 5, 6)])
    assert pkt[:4] == bytes([0xBB, 0x00, 8, 0xB0])
    assert pkt[4:12] == bytes([0, 2, 1, 2, 3, 4, 5, 6])
    xor = 0
    for b in pkt[:-1]:
        xor ^= b
    assert pkt[-1] == xor


def test_chase_frame_rotates_and_wraps():
    g, o = probe.GREEN, probe.GOLD
    assert probe.chase_frame(6, 0, 2, (g, o)) == [g, g, o, o, g, g]
    assert probe.chase_frame(6, 1, 2, (g, o)) == [o, g, g, o, o, g]
    assert probe.chase_frame(6, 4, 2, (g, o)) == probe.chase_frame(6, 0, 2, (g, o))


def test_speed_cap():
    probe.check_speed(10, 5)
    with pytest.raises(ValueError):
        probe.check_speed(10, 4)


async def test_probe_enables_streams_then_disables_and_restores(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(probe.asyncio, "sleep", instant)
    t = FakeTransport()
    args = SimpleNamespace(ip="10.0.0.5", port=4003, segments=6, chunk=2, speed=2.0, seconds=0.0)
    assert await probe.probe(args, t) == 0
    cmds = [m["cmd"] for m in t.sent]
    assert cmds[-1] == "colorwc"  # restore last
    assert "razer" in cmds
