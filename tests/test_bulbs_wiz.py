from types import SimpleNamespace

import pytest
from pywizlight.exceptions import WizLightTimeOutError

from app.bulbs.base import Pattern, Step
from app.bulbs.wiz import BulbUnreachable, WizBulb, WizSnapshot, pilot_for


def state(on=True, rgb=(None, None, None), bri=255, temp=2700, scene=0):
    return SimpleNamespace(
        get_state=lambda: on, get_rgb=lambda: rgb, get_brightness=lambda: bri,
        get_colortemp=lambda: temp, get_scene_id=lambda: scene,
    )


class FakeLight:
    def __init__(self, ip, port=38899, mac=None, signing_key=None, dead_ips=()):
        self.ip, self.dead_ips = ip, dead_ips
        self.sent = []
        self.st = state()

    def _check(self):
        if self.ip in self.dead_ips:
            raise WizLightTimeOutError("timeout")

    async def turn_on(self, pilot):
        self._check()
        self.sent.append(("on", pilot.pilot_params))

    async def turn_off(self):
        self._check()
        self.sent.append(("off",))

    async def updateState(self):
        self._check()
        return [self.st]


def make(dead=("1.1.1.1",), found=None, mac="CC:40:85:E6:92:F4"):
    lights = []

    def factory(ip, **kw):
        light = FakeLight(ip, dead_ips=dead, **kw)
        lights.append(light)
        return light

    async def discover(**kw):
        return found or []

    bulb = WizBulb("lamp", "1.1.1.1", mac=mac, light_factory=factory, discover=discover)
    return bulb, lights


async def test_normal_command_no_discovery():
    bulb, lights = make(dead=())
    await bulb.set_color((0, 255, 0), 200)
    assert lights[0].sent[0][0] == "on" and len(lights) == 1


async def test_rediscovers_new_ip_by_mac_and_retries():
    found = [SimpleNamespace(ip="2.2.2.2", mac="cc4085e692f4")]
    bulb, lights = make(found=found)
    await bulb.set_color((0, 255, 0))
    assert bulb.ip == "2.2.2.2"
    assert lights[-1].ip == "2.2.2.2" and lights[-1].sent


async def test_unreachable_when_mac_not_found():
    bulb, _ = make(found=[SimpleNamespace(ip="3.3.3.3", mac="aaaaaaaaaaaa")])
    with pytest.raises(BulbUnreachable):
        await bulb.set_color((0, 255, 0))


async def test_unreachable_without_mac_no_discovery():
    bulb, _ = make(mac=None, found=[SimpleNamespace(ip="2.2.2.2", mac="x")])
    with pytest.raises(BulbUnreachable):
        await bulb.snapshot()


async def test_snapshot_restore_roundtrip_and_off():
    bulb, lights = make(dead=())
    snap = await bulb.snapshot()
    assert snap == WizSnapshot(True, None, 255, 2700, 0)
    await bulb.restore(snap)
    assert lights[0].sent[-1][1]["temp"] == 2700
    await bulb.restore(WizSnapshot(False, None, 255, 2700, 0))
    assert lights[0].sent[-1] == ("off",)


def test_pilot_for_priority():
    assert pilot_for(WizSnapshot(True, (1, 2, 3), 50, 2700, 4)).pilot_params["sceneId"] == 4
    assert "r" in pilot_for(WizSnapshot(True, (10, 20, 30), 50, 2700, 0)).pilot_params
    assert pilot_for(WizSnapshot(False, None, 1, None, 0)) is None


async def test_flash_sends_each_step():
    bulb, lights = make(dead=())

    async def nosleep(t):
        pass

    bulb._sleep = nosleep
    await bulb.flash(Pattern((Step((0, 255, 0), 0.6), Step((255, 182, 18), 0.6))))
    assert len(lights[0].sent) == 2
