"""Phase 0 probe: exercise a WiZ bulb over local UDP control.

Discovers the bulb (or uses --ip), prints IP/MAC/type, snapshots its state,
measures command round-trip time, runs the green/gold pulse, optionally runs a
burst test, and restores the bulb.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass

from pywizlight import PilotBuilder, wizlight
from pywizlight.discovery import discover_lights
from pywizlight.exceptions import WizLightConnectionError, WizLightError

GREEN = (0, 255, 0)
GOLD = (255, 182, 18)
MAX_CHANGES_PER_S = 2.0
LATE_S = 1.0


@dataclass
class Snapshot:
    on: bool
    rgb: tuple[int, int, int] | None
    brightness: int | None
    colortemp: int | None
    scene_id: int | None


def snapshot(state) -> Snapshot:
    """Capture what is needed to restore a bulb from a pywizlight PilotParser."""
    rgb = state.get_rgb()
    if rgb is None or None in tuple(rgb):
        rgb = None
    else:
        rgb = tuple(int(v) for v in rgb)
    return Snapshot(
        on=bool(state.get_state()),
        rgb=rgb,
        brightness=state.get_brightness(),
        colortemp=state.get_colortemp(),
        scene_id=state.get_scene_id(),
    )


def snapshot_to_pilot(snap: Snapshot) -> PilotBuilder | None:
    """PilotBuilder that restores a snapshot, or None if the bulb was off."""
    if not snap.on:
        return None
    if snap.scene_id:
        return PilotBuilder(scene=snap.scene_id, brightness=snap.brightness)
    if snap.rgb and any(snap.rgb):
        return PilotBuilder(rgb=snap.rgb, brightness=snap.brightness)
    if snap.colortemp:
        return PilotBuilder(colortemp=snap.colortemp, brightness=snap.brightness)
    return PilotBuilder(brightness=snap.brightness)


def pulse_steps(color_a, color_b, pulses: int, duration_s: float) -> list[tuple[tuple, float]]:
    """(color, hold_seconds) steps alternating a/b: 2 color changes per pulse."""
    n = pulses * 2
    hold = duration_s / n
    if 1.0 / hold > MAX_CHANGES_PER_S:
        raise ValueError(f"pulse too fast: {1.0 / hold:.1f} changes/s > {MAX_CHANGES_PER_S:g}")
    return [((color_a if i % 2 == 0 else color_b), hold) for i in range(n)]


def rtt_stats(samples: list[float]) -> str:
    if not samples:
        return "no samples"
    s = sorted(samples)
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
    return (
        f"n={len(s)} min={s[0] * 1000:.0f}ms median={statistics.median(s) * 1000:.0f}ms "
        f"p95={p95 * 1000:.0f}ms max={s[-1] * 1000:.0f}ms"
    )


async def find_bulb(args: argparse.Namespace) -> wizlight:
    if args.ip:
        return wizlight(args.ip, mac=args.mac, signing_key=args.signing_key)
    print(f"Discovering via broadcast {args.broadcast} ...")
    bulbs = await discover_lights(broadcast_space=args.broadcast, wait_time=5)
    if args.mac:
        bulbs = [b for b in bulbs if (b.mac or "").lower() == args.mac.lower()]
    if not bulbs:
        sys.exit("No bulb found. Try --ip, a different --broadcast, or enable local "
                 "communication in the WiZ app.")
    for b in bulbs:
        print(f"  found {b.ip}  mac {b.mac}")
    bulb = bulbs[0]
    if args.signing_key:
        bulb = wizlight(bulb.ip, mac=bulb.mac, signing_key=args.signing_key)
    return bulb


async def timed(coro) -> tuple[float, bool]:
    """Run a bulb command; return (elapsed seconds, ok)."""
    t0 = time.monotonic()
    try:
        await coro
        return time.monotonic() - t0, True
    except Exception as e:  # timeouts and connection errors both count as failures
        print(f"    command failed: {type(e).__name__}: {e}", file=sys.stderr)
        return time.monotonic() - t0, False


async def measure_rtt(bulb: wizlight, count: int) -> None:
    reads, writes, failed = [], [], 0
    for i in range(count):
        dt, ok = await timed(_read(bulb))
        if ok:
            reads.append(dt)
        failed += not ok
        dt, ok = await timed(bulb.turn_on(PilotBuilder(rgb=GREEN, brightness=60 + i % 2 * 10)))
        if ok:
            writes.append(dt)
        failed += not ok
        await asyncio.sleep(0.3)
    print(f"  read  (getPilot): {rtt_stats(reads)}")
    print(f"  write (setPilot): {rtt_stats(writes)}")
    print(f"  failures: {failed}")


async def _read(bulb: wizlight):
    # updateState may serve cached push state; send getPilot directly for a true round trip.
    return await bulb.send({"method": "getPilot", "params": {}})


async def run_pulse(bulb: wizlight, green=GREEN) -> None:
    for color, hold in pulse_steps(green, GOLD, pulses=5, duration_s=6.0):
        await bulb.turn_on(PilotBuilder(rgb=color, brightness=255))
        await asyncio.sleep(hold)


async def burst(bulb: wizlight, rates: list[float], count: int) -> None:
    print("  rate/s  sent  timeout  late(>1s)  max")
    for rate in rates:
        tasks, t0 = [], time.monotonic()
        for i in range(count):
            await asyncio.sleep(max(0.0, t0 + i / rate - time.monotonic()))
            tasks.append(asyncio.create_task(
                timed(bulb.turn_on(PilotBuilder(brightness=30 + (i % 2) * 10)))))
        results = await asyncio.gather(*tasks)
        timeouts = sum(1 for _, ok in results if not ok)
        late = sum(1 for dt, ok in results if ok and dt > LATE_S)
        worst = max(dt for dt, _ in results)
        print(f"  {rate:6g}  {count:4d}  {timeouts:7d}  {late:9d}  {worst * 1000:.0f}ms")
        await asyncio.sleep(2)


async def restore(bulb: wizlight, snap: Snapshot) -> None:
    pilot = snapshot_to_pilot(snap)
    if pilot is None:
        await bulb.turn_off()
    else:
        await bulb.turn_on(pilot)


async def probe(args: argparse.Namespace) -> None:
    bulb = await find_bulb(args)
    state = await bulb.updateState()
    if not state or state[0] is None:
        sys.exit(f"Bulb at {bulb.ip} did not answer getPilot (port 38899). Check that local "
                 "communication is enabled in the WiZ app and the bulb is on this LAN.")
    mac = bulb.mac or await bulb.getMac()
    bulbtype = await bulb.get_bulbtype()
    print(f"Bulb: ip {bulb.ip}  mac {mac}  type {bulbtype.name} (port {bulb.port})")
    snap = snapshot(state[0])
    print(f"Snapshot: {snap}")
    try:
        if not args.pulse_only:
            print("\nRound-trip time:")
            await measure_rtt(bulb, args.rtt_count)
        print(f"\nGreen/gold pulse (5x over ~6 s), green={args.green} ... watch the bulb.")
        await run_pulse(bulb, args.green)
        if args.burst:
            print("\nWARNING: the burst test flickers the bulb rapidly (low contrast).")
            if input("Anyone photosensitive nearby? Type 'go' to proceed: ").strip() == "go":
                await burst(bulb, args.burst_rates, args.burst_count)
            else:
                print("Skipped burst test.")
    except WizLightConnectionError as e:
        print(f"\nBulb rejected a command: {e}", file=sys.stderr)
        if "-32602" in str(e):
            print("Invalid params on even a plain command usually means the firmware now "
                  "requires signed requests. Get the udp_signing_key from the WiZ app's local "
                  "integration export and pass --signing-key.", file=sys.stderr)
    finally:
        print("\nRestoring bulb ...")
        try:
            await restore(bulb, snap)
            print("Done.")
        except WizLightError as e:
            print(f"Restore FAILED ({e}); reset the bulb from the WiZ app.", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ip", help="bulb IP; skips discovery")
    p.add_argument("--mac", help="select (or record) the bulb by MAC")
    p.add_argument("--broadcast", default="255.255.255.255", help="broadcast address")
    p.add_argument("--signing-key", help="udp_signing_key hex, for firmware that needs it")
    p.add_argument("--green", default="0,255,0", help="green as R,G,B (0-255) to try")
    p.add_argument("--pulse-only", action="store_true", help="skip the round-trip test")
    p.add_argument("--rtt-count", type=int, default=10)
    p.add_argument("--burst", action="store_true", help="run the (flickery) burst test")
    p.add_argument("--burst-rates", default="2,5,10", help="commands/sec, comma-separated")
    p.add_argument("--burst-count", type=int, default=20)
    args = p.parse_args()
    try:
        args.burst_rates = [float(r) for r in args.burst_rates.split(",")]
    except ValueError:
        p.error("--burst-rates must be comma-separated numbers")
    try:
        args.green = tuple(int(v) for v in args.green.split(","))
        if len(args.green) != 3 or not all(0 <= v <= 255 for v in args.green):
            raise ValueError
    except ValueError:
        p.error("--green must be R,G,B with values 0-255")
    try:
        asyncio.run(probe(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
