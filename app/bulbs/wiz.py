"""WiZ bulb adapter over pywizlight (local UDP, port 38899).

The bulb must have "only allow verified controls" turned off in the WiZ app,
or be given the udp_signing_key as `signing_key`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pywizlight import PilotBuilder, wizlight
from pywizlight.discovery import discover_lights
from pywizlight.exceptions import WizLightError

from app.bulbs.base import BulbAdapter, Color, Sleep

log = logging.getLogger(__name__)


class BulbUnreachable(RuntimeError):
    pass


async def discover_wiz(
    broadcast: str = "255.255.255.255",
    wait_time: float = 5,
    discover: Callable[..., Awaitable[list]] = discover_lights,
) -> list[dict]:
    """WiZ bulbs answering a LAN broadcast: [{"ip", "mac"}], one per MAC, sorted by IP."""
    try:
        found = await discover(broadcast_space=broadcast, wait_time=wait_time)
    except (OSError, WizLightError) as e:
        raise BulbUnreachable(f"discovery failed: {e}") from e
    by_mac: dict[str, dict] = {}
    for b in found:
        mac = (b.mac or "").lower().replace(":", "")
        by_mac.setdefault(mac or b.ip, {"ip": b.ip, "mac": mac})
    def ip_key(b: dict) -> tuple:
        return tuple(int(p) if p.isdigit() else 0 for p in b["ip"].split("."))

    return sorted(by_mac.values(), key=ip_key)


@dataclass(frozen=True)
class WizSnapshot:
    on: bool
    rgb: Color | None
    brightness: int | None
    colortemp: int | None
    scene_id: int | None


def snapshot_from_state(state: Any) -> WizSnapshot:
    rgb = state.get_rgb()
    rgb = None if rgb is None or None in tuple(rgb) else tuple(int(v) for v in rgb)
    return WizSnapshot(
        on=bool(state.get_state()),
        rgb=rgb,
        brightness=state.get_brightness(),
        colortemp=state.get_colortemp(),
        scene_id=state.get_scene_id(),
    )


def pilot_for(snap: WizSnapshot) -> PilotBuilder | None:
    """Builder that restores a snapshot; None means the bulb was off."""
    if not snap.on:
        return None
    if snap.scene_id:
        return PilotBuilder(scene=snap.scene_id, brightness=snap.brightness)
    if snap.rgb and any(snap.rgb):
        return PilotBuilder(rgb=snap.rgb, brightness=snap.brightness)
    if snap.colortemp:
        return PilotBuilder(colortemp=snap.colortemp, brightness=snap.brightness)
    return PilotBuilder(brightness=snap.brightness)


class WizBulb(BulbAdapter):
    def __init__(
        self,
        name: str,
        ip: str,
        mac: str | None = None,
        port: int = 38899,
        signing_key: str | None = None,
        light_factory: Callable[..., Any] = wizlight,
        discover: Callable[..., Awaitable[list]] = discover_lights,
        broadcast: str = "255.255.255.255",
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        super().__init__(name, sleep)
        self.ip = ip
        self.mac = mac.lower().replace(":", "") if mac else None
        self._port = port
        self._signing_key = signing_key
        self._factory = light_factory
        self._discover = discover
        self._broadcast = broadcast
        self._light = self._make_light()

    def _make_light(self) -> Any:
        return self._factory(
            self.ip, port=self._port, mac=self.mac, signing_key=self._signing_key
        )

    async def _rediscover(self) -> bool:
        if not self.mac:
            return False
        log.warning("[%s] %s not answering; searching for MAC %s", self.name, self.ip, self.mac)
        for found in await self._discover(broadcast_space=self._broadcast, wait_time=5):
            if (found.mac or "").lower().replace(":", "") == self.mac:
                if found.ip != self.ip:
                    log.warning("[%s] bulb moved %s -> %s", self.name, self.ip, found.ip)
                self.ip = found.ip
                self._light = self._make_light()
                return True
        return False

    async def _call(self, fn: Callable[[Any], Awaitable[Any]]) -> Any:
        """Run a command; on failure re-discover by MAC and retry once."""
        try:
            return await fn(self._light)
        except WizLightError as first:
            if not await self._rediscover():
                raise BulbUnreachable(f"{self.name} at {self.ip}: {first}") from first
        try:
            return await fn(self._light)
        except WizLightError as second:
            raise BulbUnreachable(f"{self.name} at {self.ip}: {second}") from second

    async def ping(self) -> float | None:
        """One direct getPilot (no cache, no re-discovery); never changes the bulb."""
        t0 = time.monotonic()
        try:
            resp = await self._light.send({"method": "getPilot", "params": {}})
        except WizLightError:
            return None
        return time.monotonic() - t0 if resp and "result" in resp else None

    async def set_color(self, color: Color, brightness: int = 255) -> None:
        await self._call(lambda b: b.turn_on(PilotBuilder(rgb=color, brightness=brightness)))

    async def snapshot(self) -> WizSnapshot:
        async def read(b: Any) -> Any:
            state = await b.updateState()
            if not state or state[0] is None:
                raise WizLightError("no state returned")
            return state[0]

        return snapshot_from_state(await self._call(read))

    async def restore(self, snapshot: WizSnapshot) -> None:
        pilot = pilot_for(snapshot)
        if pilot is None:
            await self._call(lambda b: b.turn_off())
        else:
            await self._call(lambda b: b.turn_on(pilot))
