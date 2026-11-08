"""Govee bulb/strip adapter over Govee's LAN API (UDP, no cloud).

Turn on "LAN Control" for the device in the Govee Home app first; only some models support it.
Commands go to ip:4003. Status and scan replies come back unicast to local port 4002, a port every
reply shares, so anything that listens on it takes one module-level lock. Discovery sends a scan to
the multicast group 239.255.255.250:4001; adding by static IP skips it.

devStatus reports on/off, brightness, color and color temperature only. Scenes, music and DIY modes
are not reported, so a strip left in one comes back from restore() as a plain color.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import socket
import struct
import time
from dataclasses import dataclass
from typing import Protocol

from app.bulbs.base import (
    BulbAdapter,
    Color,
    PatternError,
    SegmentPattern,
    Sleep,
    capabilities_for,
)
from app.bulbs.wiz import BulbUnreachable

log = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.255.250"
SCAN_PORT = 4001
REPLY_PORT = 4002
COMMAND_PORT = 4003
RAZER_ENABLE = 0xB1
RAZER_LED_DATA = 0xB0
RAZER_SETTLE_S = 0.3
STATUS_TIMEOUT_S = 2.0
STATUS_ATTEMPTS = 2
SCAN_WAIT_S = 3.0
SCAN_RESEND_S = 1.0

_reply_port_lock = asyncio.Lock()


def _norm_id(device_id: str | None) -> str:
    return (device_id or "").lower().replace(":", "")


class GoveeTransport(Protocol):
    async def send(self, ip: str, port: int, payload: dict) -> None: ...

    async def query(
        self, ip: str, port: int, payload: dict, expect: str, timeout: float
    ) -> dict | None:
        """Send and wait for a reply with `msg.cmd == expect` from `ip`; its `data`, or None."""

    async def scan(self, wait_time: float) -> list[dict]:
        """`data` of every scan reply heard within wait_time."""


class _Inbox(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[bytes, str]] = asyncio.Queue()

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.queue.put_nowait((data, addr[0]))


def _decode(raw: bytes) -> dict | None:
    try:
        msg = json.loads(raw)["msg"]
        return {"cmd": msg["cmd"], "data": msg.get("data") or {}}
    except (ValueError, KeyError, TypeError):
        return None


class UdpTransport:
    """The real thing: plain UDP sockets."""

    async def send(self, ip: str, port: int, payload: dict) -> None:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, remote_addr=(ip, port)
        )
        try:
            transport.sendto(json.dumps(payload).encode())
        finally:
            transport.close()

    async def query(
        self, ip: str, port: int, payload: dict, expect: str, timeout: float
    ) -> dict | None:
        loop = asyncio.get_running_loop()
        async with _reply_port_lock:
            transport, inbox = await loop.create_datagram_endpoint(
                _Inbox, local_addr=("0.0.0.0", REPLY_PORT), reuse_port=True
            )
            try:
                transport.sendto(json.dumps(payload).encode(), (ip, port))
                deadline = loop.time() + timeout
                while (left := deadline - loop.time()) > 0:
                    try:
                        raw, src = await asyncio.wait_for(inbox.queue.get(), left)
                    except TimeoutError:
                        return None
                    msg = _decode(raw)
                    if src == ip and msg and msg["cmd"] == expect:
                        return msg["data"]
                return None
            finally:
                transport.close()
                await asyncio.sleep(0)  # let the loop close the socket before the next bind

    async def scan(self, wait_time: float) -> list[dict]:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", REPLY_PORT))
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
            struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.setblocking(False)
        probe = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()
        found: list[dict] = []
        async with _reply_port_lock:
            transport, inbox = await loop.create_datagram_endpoint(_Inbox, sock=sock)
            try:
                end = loop.time() + wait_time
                next_send = 0.0
                while (left := end - loop.time()) > 0:
                    if loop.time() >= next_send:
                        transport.sendto(probe, (MULTICAST_GROUP, SCAN_PORT))
                        next_send = loop.time() + SCAN_RESEND_S
                    try:
                        raw, _ = await asyncio.wait_for(
                            inbox.queue.get(), min(left, max(0.05, next_send - loop.time()))
                        )
                    except TimeoutError:
                        continue
                    msg = _decode(raw)
                    if msg and msg["cmd"] == "scan" and msg["data"].get("ip"):
                        found.append(msg["data"])
            finally:
                transport.close()
                await asyncio.sleep(0)
        return found


def _sort_key(b: dict) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in b["ip"].split("."))


async def discover_govee(
    wait_time: float = SCAN_WAIT_S, transport: GoveeTransport | None = None
) -> list[dict]:
    """Govee devices answering a LAN scan: [{"ip", "mac"}], one per device id, sorted by IP.

    Govee has no MAC in the scan reply, so `mac` carries the device id (lowercase, no colons)."""
    try:
        replies = await (transport or UdpTransport()).scan(wait_time)
    except OSError as e:
        raise BulbUnreachable(f"discovery failed: {e}") from e
    by_id: dict[str, dict] = {}
    for r in replies:
        ident = _norm_id(r.get("device"))
        by_id.setdefault(ident or r["ip"], {"ip": r["ip"], "mac": ident})
    return sorted(by_id.values(), key=_sort_key)


@dataclass(frozen=True)
class GoveeSnapshot:
    on: bool
    rgb: Color
    brightness: int  # Govee scale, 1..100
    colortemp: int  # Kelvin; 0 when the strip was showing a color


def snapshot_from_status(data: dict) -> GoveeSnapshot:
    c = data.get("color") or {}
    return GoveeSnapshot(
        on=bool(data.get("onOff")),
        rgb=(int(c.get("r", 0)), int(c.get("g", 0)), int(c.get("b", 0))),
        brightness=max(1, min(100, int(data.get("brightness", 100)))),
        colortemp=int(data.get("colorTemInKelvin", 0) or 0),
    )


def govee_brightness(brightness: int) -> int:
    """Pattern brightness 1..255 -> Govee 1..100."""
    return max(1, min(100, round(brightness * 100 / 255)))


def _msg(cmd: str, data: dict) -> dict:
    return {"msg": {"cmd": cmd, "data": data}}


def razer_packet(command: int, data: list[int]) -> bytes:
    """`BB 00 <size> <command> <data> <xor of every earlier byte>`."""
    body = bytes([0xBB, 0x00, len(data), command, *data])
    checksum = 0
    for b in body:
        checksum ^= b
    return body + bytes([checksum])


def razer_message(packet: bytes) -> dict:
    return _msg("razer", {"pt": base64.b64encode(packet).decode()})


class GoveeBulb(BulbAdapter):
    def __init__(
        self,
        name: str,
        ip: str,
        mac: str | None = None,
        port: int = COMMAND_PORT,
        sleep: Sleep = asyncio.sleep,
        transport: GoveeTransport | None = None,
        timeout_s: float = STATUS_TIMEOUT_S,
        attempts: int = STATUS_ATTEMPTS,
        segments: int = 1,
    ) -> None:
        super().__init__(name, sleep)
        self.capabilities = capabilities_for("govee", segments)
        self.ip = ip
        self.mac = _norm_id(mac) or None
        self._port = port
        self._transport = transport or UdpTransport()
        self._timeout = timeout_s
        self._attempts = attempts
        self._on: bool | None = None
        self._brightness: int | None = None

    async def _send(self, cmd: str, data: dict) -> None:
        try:
            await self._transport.send(self.ip, self._port, _msg(cmd, data))
        except OSError as e:
            raise BulbUnreachable(f"{self.name} at {self.ip}: {e}") from e

    async def _status(self) -> dict | None:
        for _ in range(self._attempts):
            try:
                data = await self._transport.query(
                    self.ip, self._port, _msg("devStatus", {}), "devStatus", self._timeout
                )
            except OSError as e:
                raise BulbUnreachable(f"{self.name} at {self.ip}: {e}") from e
            if data is not None:
                return data
        return None

    async def _turn(self, on: bool) -> None:
        await self._send("turn", {"value": 1 if on else 0})
        self._on = on

    async def _set_brightness(self, value: int) -> None:
        if value != self._brightness:
            await self._send("brightness", {"value": value})
            self._brightness = value

    async def ping(self) -> float | None:
        t0 = time.monotonic()
        try:
            data = await self._status()
        except BulbUnreachable:
            return None
        return time.monotonic() - t0 if data is not None else None

    async def set_color(self, color: Color, brightness: int = 255) -> None:
        if self._on is not True:
            await self._turn(True)
        await self._set_brightness(govee_brightness(brightness))
        r, g, b = color
        await self._send("colorwc", {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0})

    async def play_segments(self, pattern: SegmentPattern) -> None:
        """Per-segment frames over the unofficial "razer" streaming mode (not in Govee's documented
        LAN API; verified on the H616D). Streaming applies instantly, with none of the fade that
        normal commands go through, and the strip leaves the mode by itself after about a minute
        without frames. It is switched off again here; the caller restores the strip afterward."""
        if pattern.segments != self.capabilities.segments:
            raise PatternError(
                f"{self.name} has {self.capabilities.segments} segments, pattern has "
                f"{pattern.segments}"
            )
        if self._on is not True:
            await self._turn(True)
        await self._set_brightness(govee_brightness(pattern.brightness))
        await self._send_packet(razer_packet(RAZER_ENABLE, [1]))
        await self._sleep(RAZER_SETTLE_S)
        try:
            for frame in pattern.frames:
                t0 = time.monotonic()
                rgb = [v for c in frame.colors for v in c]
                await self._send_packet(razer_packet(RAZER_LED_DATA, [0, len(frame.colors), *rgb]))
                await self._sleep(max(0.0, frame.hold_s - (time.monotonic() - t0)))
        finally:
            await self._send_packet(razer_packet(RAZER_ENABLE, [0]))

    async def _send_packet(self, packet: bytes) -> None:
        msg = razer_message(packet)["msg"]
        await self._send(msg["cmd"], msg["data"])

    async def snapshot(self) -> GoveeSnapshot:
        data = await self._status()
        if data is None:
            raise BulbUnreachable(f"{self.name} at {self.ip}: no answer (is LAN Control on?)")
        snap = snapshot_from_status(data)
        self._on, self._brightness = snap.on, snap.brightness
        return snap

    async def restore(self, snapshot: GoveeSnapshot) -> None:
        if not snapshot.on:
            await self._turn(False)
            return
        if self._on is not True:
            await self._turn(True)
        if snapshot.colortemp > 0:
            color = {"r": 0, "g": 0, "b": 0}
            await self._send("colorwc", {"color": color, "colorTemInKelvin": snapshot.colortemp})
        else:
            r, g, b = snapshot.rgb
            await self._send("colorwc", {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0})
        await self._set_brightness(snapshot.brightness)
