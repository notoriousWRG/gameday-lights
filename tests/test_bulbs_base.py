import asyncio

import pytest

from app.bulbs.base import DryRunBulb, Pattern, PatternError, Step

G, Y = (0, 255, 0), (255, 182, 18)


def test_hold_at_cap_ok_below_rejected():
    Pattern((Step(G, 0.5), Step(Y, 0.5)))
    with pytest.raises(PatternError):
        Pattern((Step(G, 0.4),))


@pytest.mark.parametrize("step", [Step((0, 300, 0), 1), Step(G, 1, brightness=0), Step(G, 1, 256)])
def test_invalid_values_rejected(step):
    with pytest.raises(PatternError):
        Pattern((step,))


def test_empty_rejected():
    with pytest.raises(PatternError):
        Pattern(())


def test_duration():
    assert Pattern((Step(G, 0.6), Step(Y, 0.6))).duration_s == pytest.approx(1.2)


async def test_flash_applies_steps_with_sleeps():
    slept = []

    async def sleep(t):
        slept.append(t)

    bulb = DryRunBulb("lamp", sleep=sleep)
    await bulb.flash(Pattern((Step(G, 0.6), Step(Y, 0.7, 200))))
    assert bulb.calls == [("set_color", G, 255), ("set_color", Y, 200)]
    assert slept == pytest.approx([0.6, 0.7], abs=0.05)


async def test_flash_subtracts_command_time():
    slept = []

    async def sleep(t):
        slept.append(t)

    class Slow(DryRunBulb):
        async def set_color(self, color, brightness=255):
            await asyncio.sleep(0.2)

    await Slow("lamp", sleep=sleep).flash(Pattern((Step(G, 0.6),)))
    assert 0.3 < slept[0] < 0.45


async def test_dry_run_snapshot_restore():
    bulb = DryRunBulb("lamp")
    snap = await bulb.snapshot()
    await bulb.restore(snap)
    assert bulb.calls[-1] == ("restore", snap)
