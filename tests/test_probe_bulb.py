import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "probe_bulb.py"
spec = importlib.util.spec_from_file_location("probe_bulb", SCRIPT)
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_bulb"] = probe
spec.loader.exec_module(probe)


def fake_state(on=True, rgb=(None, None, None), brightness=100, temp=None, scene=None):
    return SimpleNamespace(
        get_state=lambda: on, get_rgb=lambda: rgb, get_brightness=lambda: brightness,
        get_colortemp=lambda: temp, get_scene_id=lambda: scene,
    )


def test_snapshot_rgb_and_none():
    s = probe.snapshot(fake_state(rgb=(1.0, 2.0, 3.0)))
    assert s.rgb == (1, 2, 3)
    assert probe.snapshot(fake_state()).rgb is None


def test_restore_off_returns_none():
    assert probe.snapshot_to_pilot(probe.snapshot(fake_state(on=False))) is None


def test_restore_prefers_scene_then_rgb_then_temp():
    p = probe.snapshot_to_pilot(probe.snapshot(fake_state(scene=4, rgb=(1, 2, 3))))
    assert p.pilot_params["sceneId"] == 4
    p = probe.snapshot_to_pilot(probe.snapshot(fake_state(rgb=(10, 20, 30))))
    assert {"r", "g", "b"} <= p.pilot_params.keys()  # pywizlight rescales values
    p = probe.snapshot_to_pilot(probe.snapshot(fake_state(temp=2700)))
    assert p.pilot_params["temp"] == 2700


def test_pulse_steps_default_within_cap():
    steps = probe.pulse_steps(probe.GREEN, probe.GOLD, 5, 6.0)
    assert len(steps) == 10
    assert steps[0][0] == probe.GREEN and steps[1][0] == probe.GOLD
    assert sum(h for _, h in steps) == pytest.approx(6.0)


def test_pulse_steps_rejects_too_fast():
    with pytest.raises(ValueError):
        probe.pulse_steps(probe.GREEN, probe.GOLD, 5, 3.0)


def test_rtt_stats():
    assert probe.rtt_stats([]) == "no samples"
    assert "median=200ms" in probe.rtt_stats([0.1, 0.2, 0.3])


async def test_burst_counts_failures(capsys, monkeypatch):
    class Fake:
        n = 0

        async def turn_on(self, pilot):
            self.n += 1
            if self.n == 2:
                raise TimeoutError("boom")

    real_sleep = probe.asyncio.sleep

    async def fast_sleep(t):
        await real_sleep(0)

    monkeypatch.setattr(probe.asyncio, "sleep", fast_sleep)
    await probe.burst(Fake(), [1000.0], 4)
    row = capsys.readouterr().out.splitlines()[1].split()
    assert row[:4] == ["1000", "4", "1", "0"]


def test_help():
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "--burst" in r.stdout
