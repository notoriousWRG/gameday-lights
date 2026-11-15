"""Per-bulb routes: pulse check, steady light state, and finding bulbs on the network."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request

from app.bulbs.base import BulbState, Pattern, SegmentPattern
from app.effects import parse_color, to_hex
from app.web.common import BulbGuard, iso, require_gameday, resolve

# A bulb that is off or unplugged must not hold a page request for minutes (the adapters retry and
# search the network). Long enough to wait out an effect playing on the same bulb.
STATE_READ_TIMEOUT_S = 12.0

log = logging.getLogger(__name__)


def state_json(state: BulbState) -> dict:
    return {"on": state.on, "color": to_hex(state.color), "color_temp_k": state.color_temp_k,
            "brightness": state.brightness}


def parse_state(body: object) -> BulbState:
    """A request body to a BulbState. TypeError/KeyError for the wrong shape, ValueError for
    values out of range."""
    if not isinstance(body, dict) or not body:
        raise TypeError("body must be an object with at least one field")
    extra = sorted(set(body) - {"on", "color", "color_temp_k", "brightness"})
    if extra:
        raise TypeError(f"unknown field {extra[0]!r}")
    on = body.get("on")
    if on is not None and not isinstance(on, bool):
        raise TypeError("on must be true or false")
    for key in ("color_temp_k", "brightness"):
        v = body.get(key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)):
            raise TypeError(f"{key} must be a whole number")
    color = parse_color(body["color"]) if body.get("color") else None
    return BulbState(on, color, body.get("color_temp_k"), body.get("brightness"))


def add_bulb_routes(
    app: FastAPI,
    guard: BulbGuard,
    pulse_pattern: Callable[[str], Pattern | SegmentPattern],
    dry_run: bool,
) -> None:
    dispatcher = guard.dispatcher

    @app.post("/api/bulbs/{name}/pulse")
    async def pulse(name: str, request: Request) -> dict:
        require_gameday(request)
        guard.ready(name)
        pattern = pulse_pattern(name)
        started = await guard.play(name, pattern)
        log.info("pulse check on %s (%.1fs)", name, pattern.duration_s)
        return {"ok": True, "dry_run": dry_run, "duration_s": pattern.duration_s,
                "started_at": iso(started)}

    @app.get("/api/bulbs/{name}/state")
    async def get_bulb_state(name: str) -> dict:
        guard.known(name)
        try:
            state = await asyncio.wait_for(dispatcher.current_state(name), STATE_READ_TIMEOUT_S)
        except TimeoutError:
            raise HTTPException(
                504, f"{name} is not answering (is it plugged in and on the network?)") from None
        except NotImplementedError as e:
            raise HTTPException(501, str(e)) from None
        except Exception as e:
            raise HTTPException(502, f"bulb error: {e}") from None
        return {**state_json(state), "dry_run": dry_run}

    @app.put("/api/bulbs/{name}/state")
    async def put_bulb_state(name: str, request: Request) -> dict:
        """Set a bulb's steady light settings (a manual change, not an effect)."""
        require_gameday(request)
        guard.known(name)
        try:
            state = parse_state(await request.json())
        except (TypeError, KeyError) as e:
            raise HTTPException(400, f"bad state: {e}") from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        guard.state_change(name)
        try:
            await dispatcher.set_state(name, state)
        except NotImplementedError as e:
            raise HTTPException(501, str(e)) from None
        except Exception as e:
            log.warning("state change on %s failed: %r", name, e)
            raise HTTPException(502, f"bulb error: {e}") from None
        log.info("light state on %s: %s", name, state_json(state))
        return {"ok": True, "dry_run": dry_run, "applied": state_json(state)}


def add_discover_route(app: FastAPI, discover_bulbs, cfg) -> None:
    """Find bulbs on the LAN (a ~5 s broadcast). Read-only: nothing is saved, no keys are shown."""
    running = False

    @app.post("/api/bulbs/discover")
    async def discover(request: Request) -> list[dict]:
        nonlocal running
        if request.headers.get("x-gameday") != "1":
            raise HTTPException(403, "missing X-Gameday header")
        if running:
            raise HTTPException(409, "already searching")
        running = True
        try:
            found = await discover_bulbs()
        except Exception as e:
            log.warning("bulb discovery failed: %r", e)
            raise HTTPException(502, f"discovery failed: {e}") from None
        finally:
            running = False
        stored = resolve(cfg).bulbs
        out = []
        for b in found:
            def norm(m):
                return (m or "").lower().replace(":", "")

            match = next((s for s in stored if (s.mac and norm(s.mac) == b["mac"])
                          or (not s.mac and s.ip == b["ip"])), None)
            out.append({"ip": b["ip"], "mac": b["mac"], "kind": b.get("kind", "wiz"),
                        "known": match is not None, "name": match.name if match else None,
                        "stored_ip": match.ip if match else None,
                        "moved": match is not None and match.ip != b["ip"]})
        return out
