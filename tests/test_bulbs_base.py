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


async def test_ping_reachable_and_not():
    from app.bulbs.base import BulbAdapter

    class Fake(BulbAdapter):
        def __init__(self, ok):
            super().__init__("x")
            self.ok = ok

        async def set_color(self, color, brightness=255):
            pass

        async def snapshot(self):
            if not self.ok:
                raise RuntimeError("down")
            return "s"

        async def restore(self, snapshot):
            pass

    assert (await Fake(True).ping()) is not None
    assert await Fake(False).ping() is None
    assert await DryRunBulb("d").ping() == 0.0


def test_capabilities_cannot_lower_the_cap():
    from app.bulbs.base import MIN_HOLD_S, Capabilities

    with pytest.raises(ValueError):
        Capabilities(min_hold_s=MIN_HOLD_S / 2)
    with pytest.raises(ValueError):
        Capabilities(segments=0)


def test_capabilities_for_kinds():
    from app.bulbs.base import capabilities_for

    assert capabilities_for("wiz", 20).kinds == {"pulse"}
    assert capabilities_for("wiz", 20).segments == 1
    assert capabilities_for("govee").kinds == {"pulse"}
    assert capabilities_for("govee", 20).kinds == {"pulse", "chase"}
    assert capabilities_for("govee", 20).segments == 20


def _frames(*rows, hold=0.1):
    from app.bulbs.base import SegmentFrame

    return tuple(SegmentFrame(tuple(r), hold) for r in rows)


def test_segment_pattern_duration_and_segments():
    from app.bulbs.base import SegmentPattern

    p = SegmentPattern(_frames([G, Y], [Y, G], hold=0.6))
    assert p.segments == 2
    assert p.duration_s == pytest.approx(1.2)


def test_segment_pattern_cap_is_per_segment():
    from app.bulbs.base import SegmentPattern

    # each segment changes once per 0.6 s: fine
    SegmentPattern(_frames([G, Y], [Y, G], [G, Y], hold=0.6))
    # segment 0 changes every 0.1 s: over the cap
    with pytest.raises(PatternError):
        SegmentPattern(_frames([G, Y], [Y, Y], [G, Y], hold=0.1))


def test_segment_pattern_rejects_ragged_and_empty():
    from app.bulbs.base import SegmentPattern

    with pytest.raises(PatternError):
        SegmentPattern(())
    with pytest.raises(PatternError):
        SegmentPattern(_frames([G, Y], [G]))


async def test_play_dispatches_on_pattern_type():
    from app.bulbs.base import SegmentPattern

    bulb = DryRunBulb("lamp")
    await bulb.play(Pattern((Step(G, 0.6),)))
    await bulb.play(SegmentPattern(_frames([G, Y])))
    assert [c[0] for c in bulb.calls] == ["set_color", "play_segments"]


async def test_adapter_without_segments_refuses_segment_patterns():
    from app.bulbs.base import BulbAdapter, SegmentPattern

    class Plain(BulbAdapter):
        async def set_color(self, color, brightness=255): ...
        async def snapshot(self): ...
        async def restore(self, snapshot): ...

    with pytest.raises(PatternError):
        await Plain("x").play(SegmentPattern(_frames([G])))
