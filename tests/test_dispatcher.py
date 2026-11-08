import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.bulbs.base import BulbAdapter, DryRunBulb, Pattern, Step
from app.config import BulbConfig, Config, GeneralConfig, TeamConfig
from app.dispatch.dispatcher import Dispatcher, make_planner
from app.effects import EffectConfig
from app.store import Event, Game, Store, dedupe_key

T0 = datetime(2026, 11, 8, 21, 30, tzinfo=UTC)
PATTERN = Pattern((Step((0, 255, 0), 0.5), Step((255, 182, 18), 0.5)))


class Clock:
    def __init__(self, t=T0):
        self.t = t
        self.slept = []

    def now(self):
        return self.t

    async def sleep(self, s):
        self.slept.append(s)
        self.t += timedelta(seconds=s)


class Recorder(BulbAdapter):
    def __init__(self, name, log, fail_flash=False):
        super().__init__(name, sleep=self._nosleep)
        self.log, self.fail_flash = log, fail_flash

    async def _nosleep(self, s):
        await asyncio.sleep(0)

    async def set_color(self, color, brightness=255):
        self.log.append((self.name, "set", color))
        if self.fail_flash:
            raise RuntimeError("bulb died")

    async def snapshot(self):
        self.log.append((self.name, "snapshot"))
        return "snap"

    async def restore(self, snapshot):
        self.log.append((self.name, "restore"))


def event(n=1, due_in=45, status="pending"):
    return Event(dedupe_key("g1", "9", n), "g1", "9", "score", T0,
                 T0 + timedelta(seconds=due_in), {"delta": 6}, status=status)


def setup(bulbs=("a",), fail=False, dry_run=False):
    store = Store()
    clock = Clock()
    log = []
    objs = {n: Recorder(n, log, fail_flash=fail) for n in bulbs}
    d = Dispatcher(store, objs, lambda e: [(b, PATTERN) for b in bulbs], clock.now, clock.sleep,
                   dry_run)
    return store, clock, log, d


async def test_waits_exact_delay_then_fires_and_logs():
    store, clock, log, d = setup()
    e = event(due_in=45)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert clock.slept[0] == 45
    got = store.get_event(e.dedupe_key)
    assert got.status == "fired" and got.fired_at == T0 + timedelta(seconds=45)
    assert [x[1] for x in log] == ["snapshot", "set", "set", "restore"]


async def test_dry_run_status():
    store, _, _, d = setup(dry_run=True)
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert store.get_event(e.dedupe_key).status == "dry_run"


async def test_same_bulb_effects_never_overlap():
    store, _, log, d = setup()
    for n in (1, 2):
        store.insert_event(event(n, due_in=0))
        d.schedule(event(n, due_in=0))
    await d.wait_idle()
    kinds = [x[1] for x in log]
    assert kinds == ["snapshot", "set", "set", "restore"] * 2


async def test_different_bulbs_run_in_parallel_one_event():
    store, _, log, d = setup(bulbs=("a", "b"))
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert {x[0] for x in log} == {"a", "b"}
    assert store.get_event(e.dedupe_key).status == "fired"


async def test_flash_error_still_restores_and_marks_failed():
    store, _, log, d = setup(fail=True)
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert log[-1][1] == "restore"
    assert store.get_event(e.dedupe_key).status == "failed"


async def test_recover_skips_past_due_and_schedules_future():
    store, clock, log, d = setup()
    store.insert_event(event(1, due_in=-5))
    store.insert_event(event(2, due_in=20))
    d.recover()
    await d.wait_idle()
    assert store.get_event("g1:9:1").status == "skipped_restart"
    assert store.get_event("g1:9:2").status == "fired"
    assert clock.slept == [20]


def config(color=None):
    return Config(
        GeneralConfig(True, "x.db"),
        (BulbConfig("a", "1.1.1.1"),),
        (TeamConfig("nfl", "9", "GB", ("a",), color=color),),
        EffectConfig(),
    )


def test_make_planner_uses_config_colors_over_espn():
    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    espn = {("nfl", "9"): ((32, 78, 50), (255, 182, 18))}
    plan = make_planner(config(color=(0, 255, 0)), espn, store)(event())
    assert [n for n, _ in plan] == ["a"]
    pattern = plan[0][1]
    assert pattern.steps[0].color == (0, 255, 0)
    assert pattern.steps[1].color == (255, 182, 18)
    pattern = make_planner(config(), espn, store)(event())[0][1]
    assert pattern.steps[0].color == (32, 78, 50)


def test_make_planner_unfollowed_team_raises():
    store = Store()
    store.upsert_game(Game("g1", "nfl", "x", T0, "in"))
    e = event()
    e.team_id = "99"
    with pytest.raises(LookupError):
        make_planner(config(), {}, store)(e)


async def test_planner_failure_marks_failed():
    store = Store()
    clock = Clock()
    d = Dispatcher(store, {"a": DryRunBulb("a")}, lambda e: 1 / 0, clock.now, clock.sleep)
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert store.get_event(e.dedupe_key).status == "failed"


async def test_play_now_queues_behind_an_event_and_is_not_an_event():
    store, clock, log, d = setup()
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.play_now("a", PATTERN)
    await d.wait_idle()
    assert [x[1] for x in log] == ["snapshot", "set", "set", "restore"] * 2  # never interleaved
    assert len(store.recent_events(10)) == 1


async def test_play_now_unknown_bulb():
    _, _, _, d = setup()
    with pytest.raises(KeyError):
        await d.play_now("zzz", PATTERN)


def test_make_bulb_pulse_uses_team_pattern_else_default():
    from app.dispatch.dispatcher import make_bulb_pulse

    pulse = make_bulb_pulse(config(color=(1, 2, 3)), {("nfl", "9"): ((9, 9, 9), (8, 8, 8))})
    assert pulse("a").steps[0].color == (1, 2, 3)  # team's config color wins
    assert pulse("unused-bulb").steps[0].color == (0, 255, 0)  # default effect


# --- live apply -------------------------------------------------------------------------------

def test_planner_reads_the_current_config_each_time():
    from dataclasses import replace

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    cfg_a = config(color=(1, 2, 3))
    box = {"cfg": cfg_a}
    plan = make_planner(lambda: box["cfg"], {}, store)
    assert plan(event())[0][1].steps[0].color == (1, 2, 3)
    team = replace(cfg_a.teams[0], color=(9, 9, 9))
    box["cfg"] = replace(cfg_a, teams=(team,))  # a settings edit, no restart
    assert plan(event())[0][1].steps[0].color == (9, 9, 9)


async def test_set_bulbs_swaps_the_registry_keeps_the_queue_for_staying_bulbs():
    store, clock, log, d = setup(bulbs=("a",))
    keep = d.bulbs["a"]
    lock_before = d._locks["a"]
    fresh = Recorder("b", log)
    d.set_bulbs({"a": keep, "b": fresh})
    assert set(d.bulbs) == {"a", "b"}
    assert d._locks["a"] is lock_before  # the same serial queue
    assert d._locks["b"] is not lock_before
    replacement = Recorder("a", log)  # same name, different adapter (e.g. its IP changed)
    d.set_bulbs({"a": replacement})
    assert set(d.bulbs) == {"a"} and d._locks["a"] is not lock_before


async def test_removed_bulb_fails_the_event_instead_of_crashing():
    store, clock, log, d = setup(bulbs=("a",))
    d.set_bulbs({})
    e = event(due_in=0)
    store.insert_event(e)
    d.schedule(e)
    await d.wait_idle()
    assert store.get_event(e.dedupe_key).status == "failed"


async def test_effects_stay_serial_across_a_registry_swap():
    store, clock, log, d = setup(bulbs=("a",))
    keep = d.bulbs["a"]
    for n in (1, 2):
        e = event(n, due_in=0)
        store.insert_event(e)
        d.schedule(e)
    await asyncio.sleep(0)  # the first effect is under way
    d.set_bulbs({"a": keep})  # a settings edit that leaves this bulb alone
    await d.wait_idle()
    assert [x[1] for x in log] == ["snapshot", "set", "set", "restore"] * 2


def strip_config(**team_kw):
    return Config(
        GeneralConfig(True, "x.db"),
        (BulbConfig("lamp", "1.1.1.1"), BulbConfig("strip", "1.1.1.2", kind="govee", segments=20)),
        (TeamConfig("nfl", "9", "GB", ("lamp", "strip"), **team_kw),),
        EffectConfig(),
    )


def test_planner_gives_each_bulb_its_own_pattern():
    from app.bulbs.base import SegmentPattern
    from app.effects import EffectLayer

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    cfg = strip_config(fixture_effects={"strip": EffectLayer("chase")})
    plan = dict(make_planner(cfg, {}, store)(event()))
    assert isinstance(plan["lamp"], Pattern)
    assert isinstance(plan["strip"], SegmentPattern)
    assert plan["strip"].segments == 20


def test_planner_skips_a_bulb_whose_effect_cannot_be_built_and_keeps_the_rest(caplog):
    from dataclasses import replace

    from app.effects import EffectLayer

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    cfg = strip_config(fixture_effects={"strip": EffectLayer("chase")})
    # the strip loses its segments after the effect was set (a settings edit)
    cfg = replace(cfg, bulbs=(cfg.bulbs[0], replace(cfg.bulbs[1], segments=1)))
    plan = make_planner(cfg, {}, store)(event())
    assert [n for n, _ in plan] == ["lamp"]
    assert "no effect" in caplog.text


async def test_one_event_plays_different_patterns_on_two_bulbs():
    from app.bulbs.base import SegmentPattern
    from app.effects import EffectLayer

    store = Store()
    store.upsert_game(Game("g1", "nfl", "GB @ NE", T0, "in"))
    store.insert_event(event(due_in=0))
    clock = Clock()
    lamp = DryRunBulb("lamp", sleep=clock.sleep)
    strip = DryRunBulb("strip", sleep=clock.sleep)
    cfg = strip_config(fixture_effects={"strip": EffectLayer("chase")})
    d = Dispatcher(store, {"lamp": lamp, "strip": strip},
                   make_planner(cfg, {}, store), clock.now, clock.sleep)
    d.schedule(event(due_in=0))
    await d.wait_idle()
    assert [c[0] for c in lamp.calls][:2] == ["snapshot", "set_color"]
    assert [c[0] for c in strip.calls] == ["snapshot", "play_segments", "restore"]
    assert isinstance(make_planner(cfg, {}, store)(event())[1][1], SegmentPattern)


def test_bulb_pulse_uses_the_same_resolution_as_an_event():
    from app.bulbs.base import SegmentPattern
    from app.dispatch.dispatcher import make_bulb_pulse
    from app.effects import EffectLayer

    cfg = strip_config(fixture_effects={"strip": EffectLayer("chase")})
    pulse = make_bulb_pulse(cfg, {})
    assert isinstance(pulse("strip"), SegmentPattern)
    assert isinstance(pulse("lamp"), Pattern)
