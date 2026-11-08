"""Phase 0 probe: exercise a Govee strip over its LAN API.

Finds the strip (or uses --ip), prints the raw devStatus, measures devStatus round trips, runs a
short color test and restores the strip, then checks the strip came back to the state it started in.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys

from app.bulbs.base import MIN_HOLD_S
from app.bulbs.govee import (
    COMMAND_PORT,
    GoveeBulb,
    GoveeTransport,
    UdpTransport,
    discover_govee,
)
from app.bulbs.wiz import BulbUnreachable

COLORS = [("green", (0, 255, 0)), ("gold", (255, 182, 18)), ("red", (255, 0, 0)),
          ("white", (255, 255, 255))]
HOLD_S = max(0.6, MIN_HOLD_S)


def rtt_stats(samples: list[float]) -> str:
    if not samples:
        return "no samples"
    s = sorted(samples)
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
    return (
        f"n={len(s)} min={s[0] * 1000:.0f}ms median={statistics.median(s) * 1000:.0f}ms "
        f"p95={p95 * 1000:.0f}ms max={s[-1] * 1000:.0f}ms"
    )


def diff_status(before: dict, after: dict) -> list[str]:
    """One line per devStatus field whose value changed (empty list = identical)."""
    return [
        f"{key}: {before.get(key)!r} -> {after.get(key)!r}"
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


async def find_strip(args: argparse.Namespace) -> tuple[str, str | None]:
    if args.ip:
        return args.ip, None
    print("Discovering via multicast scan ...")
    found = await discover_govee(wait_time=args.wait)
    if not found:
        sys.exit("No Govee device answered. Turn on LAN Control for it in the Govee Home app "
                 "(only some models support it), or pass --ip.")
    for d in found:
        print(f"  found {d['ip']}  id {d['mac']}")
    return found[0]["ip"], found[0]["mac"]


async def raw_status(transport: GoveeTransport, ip: str, port: int) -> dict | None:
    msg = {"msg": {"cmd": "devStatus", "data": {}}}
    for _ in range(2):
        data = await transport.query(ip, port, msg, "devStatus", 2.0)
        if data is not None:
            return data
    return None


async def probe(args: argparse.Namespace, transport: GoveeTransport | None = None) -> int:
    transport = transport or UdpTransport()
    ip, ident = await find_strip(args)
    bulb = GoveeBulb("probe", ip, ident, port=args.port, transport=transport)
    before = await raw_status(transport, ip, args.port)
    if before is None:
        print(f"{ip} did not answer devStatus on port {args.port}. Check LAN Control is on for "
              "this device in the Govee Home app and that it is on this LAN.", file=sys.stderr)
        return 1
    print(f"Strip: ip {ip}  id {ident or '(unknown)'}")
    print("Raw devStatus:")
    print(json.dumps(before, indent=2, sort_keys=True))
    print("\nRound-trip time (devStatus):")
    samples, failed = [], 0
    for _ in range(args.rtt_count):
        dt = await bulb.ping()
        if dt is None:
            failed += 1
        else:
            samples.append(dt)
        await asyncio.sleep(0.3)
    print(f"  {rtt_stats(samples)}\n  failures: {failed}")
    if args.no_color:
        return 0
    snap = await bulb.snapshot()
    print(f"\nSnapshot: {snap}")
    try:
        print("Color test (watch the strip: does it jump to each color, or fade between them?)")
        for label, color in COLORS:
            print(f"  {label} {color}")
            await bulb.set_color(color, 255)
            await asyncio.sleep(HOLD_S)
    except BulbUnreachable as e:
        print(f"\nStrip stopped answering: {e}", file=sys.stderr)
    finally:
        print("\nRestoring ...")
        try:
            await bulb.restore(snap)
            await asyncio.sleep(1.0)
            after = await raw_status(transport, ip, args.port)
            if after is None:
                print("Could not read status after restore.", file=sys.stderr)
            elif diff := diff_status(before, after):
                print("Restore differs from the starting state:")
                for line in diff:
                    print(f"  {line}")
            else:
                print("Restore: MATCH (status identical to the start)")
        except Exception as e:  # restore must report, not raise, so the user knows to reset
            print(f"Restore FAILED ({e}); reset the strip from the Govee Home app.",
                  file=sys.stderr)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", help="strip IP; skips discovery")
    p.add_argument("--port", type=int, default=COMMAND_PORT)
    p.add_argument("--wait", type=float, default=3.0, help="seconds to listen during discovery")
    p.add_argument("--rtt-count", type=int, default=10)
    p.add_argument("--no-color", action="store_true", help="read-only: skip the color test")
    args = p.parse_args()
    try:
        sys.exit(asyncio.run(probe(args)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
