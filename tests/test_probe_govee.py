import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_govee.py"
spec = importlib.util.spec_from_file_location("probe_govee", SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_govee"] = probe
spec.loader.exec_module(probe)

STATUS = {"onOff": 1, "brightness": 40, "color": {"r": 9, "g": 8, "b": 7}, "colorTemInKelvin": 0}


class FakeTransport:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.sent = []

    async def send(self, ip, port, payload):
        self.sent.append(payload["msg"])

    async def query(self, ip, port, payload, expect, timeout):
        if not self.statuses:
            return None
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    async def scan(self, wait_time):
        return []


def args(**kw):
    base = dict(ip="10.0.0.5", port=4003, wait=0.1, rtt_count=2, no_color=False)
    return SimpleNamespace(**{**base, **kw})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(probe.asyncio, "sleep", instant)


def test_rtt_stats():
    assert probe.rtt_stats([]) == "no samples"
    assert "median=200ms" in probe.rtt_stats([0.1, 0.2, 0.3])


def test_diff_status():
    assert probe.diff_status(STATUS, dict(STATUS)) == []
    after = {**STATUS, "brightness": 41, "extra": 1}
    assert probe.diff_status(STATUS, after) == ["brightness: 40 -> 41", "extra: None -> 1"]


async def test_probe_runs_colors_then_restores(capsys):
    t = FakeTransport([STATUS])
    assert await probe.probe(args(), t) == 0
    cmds = [m["cmd"] for m in t.sent]
    colorwc = [m["data"]["color"] for m in t.sent if m["cmd"] == "colorwc"]
    assert colorwc[:4] == [{"r": 0, "g": 255, "b": 0}, {"r": 255, "g": 182, "b": 18},
                           {"r": 255, "g": 0, "b": 0}, {"r": 255, "g": 255, "b": 255}]
    assert t.sent[-1]["cmd"] == "brightness" or cmds[-1] == "colorwc"
    assert colorwc[-1] == {"r": 9, "g": 8, "b": 7}  # restore sets the starting color last
    assert "MATCH" in capsys.readouterr().out


async def test_probe_no_color_is_read_only():
    t = FakeTransport([STATUS])
    assert await probe.probe(args(no_color=True), t) == 0
    assert t.sent == []


async def test_probe_no_answer_exits_nonzero(capsys):
    assert await probe.probe(args(), FakeTransport([])) == 1
    assert "did not answer" in capsys.readouterr().err
