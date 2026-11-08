"""Phase 0 probe: per-segment control of a Govee strip through its "razer" streaming mode.

Reverse-engineered, not part of Govee's documented LAN API. Enables the mode, walks chunks of two
colors down the strip, then disables the mode and restores the strip's starting state.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import sys
import time
from functools import reduce

from app.bulbs.base import MAX_CHANGES_PER_S, Color
from app.bulbs.govee import COMMAND_PORT, GoveeBulb, GoveeTransport, UdpTransport
from app.bulbs.wiz import BulbUnreachable

GREEN: Color = (0, 255, 0)
GOLD: Color = (255, 140, 0)  # less green than (255,182,18), which reads washed out on this strip
ENABLE, LED_DATA = 0xB1, 0xB0
FRAME_HZ = 10.0


def build_packet(command: int, data: list[int]) -> bytes:
    body = bytes([0xBB, 0x00, len(data), command, *data])
    return body + bytes([reduce(lambda a, b: a ^ b, body)])


def razer_message(packet: bytes) -> dict:
    return {"msg": {"cmd": "razer", "data": {"pt": base64.b64encode(packet).decode()}}}


def led_frame(colors: list[Color]) -> bytes:
    return build_packet(LED_DATA, [0, len(colors), *(c for rgb in colors for c in rgb)])


def chase_frame(n: int, offset: int, chunk: int, colors: tuple[Color, Color]) -> list[Color]:
    """n segments: chunks of `chunk` alternating the two colors, shifted by `offset` (wraps)."""
    return [colors[((i - offset) // chunk) % 2] for i in range(n)]


def check_speed(speed: float, chunk: int) -> None:
    """A segment changes color once per `chunk` pixels of travel."""
    changes = speed / chunk
    if changes > MAX_CHANGES_PER_S + 1e-9:
        raise ValueError(
            f"{changes:g} color changes/sec per segment exceeds the {MAX_CHANGES_PER_S:g} cap; "
            "lower --speed or raise --chunk"
        )


async def stream(transport: GoveeTransport, ip: str, port: int, args: argparse.Namespace) -> None:
    send = lambda pkt: transport.send(ip, port, razer_message(pkt))  # noqa: E731
    await send(build_packet(ENABLE, [1]))
    await asyncio.sleep(0.3)
    start, frame = time.monotonic(), 0
    while (now := time.monotonic()) - start < args.seconds:
        offset = int((now - start) * args.speed)
        colors = chase_frame(args.segments, offset, args.chunk, (GREEN, GOLD))
        await send(led_frame(colors))
        frame += 1
        await asyncio.sleep(max(0.0, start + frame / FRAME_HZ - time.monotonic()))


async def probe(args: argparse.Namespace, transport: GoveeTransport | None = None) -> int:
    check_speed(args.speed, args.chunk)
    transport = transport or UdpTransport()
    bulb = GoveeBulb("probe", args.ip, port=args.port, transport=transport)
    try:
        snap = await bulb.snapshot()
    except BulbUnreachable as e:
        print(f"{args.ip} did not answer: {e}", file=sys.stderr)
        return 1
    print(f"Snapshot: {snap}")
    print(f"Chase: {args.segments} segments, chunks of {args.chunk}, {args.speed:g}/s, "
          f"{args.seconds:g} s. Watch the strip.")
    try:
        await stream(transport, args.ip, args.port, args)
    finally:
        print("Disabling streaming mode and restoring ...")
        try:
            await transport.send(args.ip, args.port, razer_message(build_packet(ENABLE, [0])))
            await asyncio.sleep(0.5)
            await bulb.restore(snap)
            print("Done.")
        except Exception as e:
            print(f"Restore FAILED ({e}); reset the strip from the Govee Home app.",
                  file=sys.stderr)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", required=True)
    p.add_argument("--port", type=int, default=COMMAND_PORT)
    p.add_argument("--segments", type=int, default=10, help="segment count to send per frame")
    p.add_argument("--chunk", type=int, default=3, help="segments per color chunk")
    p.add_argument("--speed", type=float, default=3.0, help="segments per second")
    p.add_argument("--seconds", type=float, default=8.0)
    args = p.parse_args()
    try:
        sys.exit(asyncio.run(probe(args)))
    except ValueError as e:
        p.error(str(e))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
