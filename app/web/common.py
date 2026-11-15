"""Shared pieces of the web app: small helpers and the guard that keeps one effect or manual
change at a time on a bulb."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from fastapi import HTTPException, Request

from app.bulbs.base import Pattern, SegmentPattern
from app.config import Config
from app.dispatch.dispatcher import Dispatcher
from app.effects import parse_color
from app.settings import error_location

log = logging.getLogger(__name__)
STATE_MIN_GAP_S = 0.5  # the effects ceiling (2 changes/sec) applies to manual changes too


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def color_or_none(value):
    """"#rrggbb" -> a color, null or "" -> None; anything else is a ValueError (a 400)."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("color must be text")
    return parse_color(value)


def resolve[T](value: T | Callable[[], T]) -> T:
    return value() if callable(value) else value


def require_gameday(request: Request) -> None:
    """Every write needs this header: a cross-site form post cannot set it without a CORS
    preflight, which this app never answers."""
    if request.headers.get("x-gameday") != "1":
        raise HTTPException(403, "missing X-Gameday header")


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise HTTPException(428, "If-Match: <revision> is required")
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError:
        raise HTTPException(400, "If-Match must be the revision number you loaded") from None


def error_item(message: str) -> dict:
    """A ConfigError message looks like "teams[0].bulbs: unknown bulb 'x'": split the path from
    the text and say which section's editor the field belongs to."""
    path, sep, text = message.partition(": ")
    if not sep:
        return {"section": "", "path": "", "message": message}
    section, field = error_location(path)
    return {"section": section, "path": field, "message": text}


class BulbGuard:
    """Who may play on a bulb right now: one effect at a time, a cooldown between pulse checks,
    and a minimum gap between manual light changes."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        cfg: Config | Callable[[], Config],
        bulbs: dict | Callable[[], dict],
        clock: Callable[[], float],
    ) -> None:
        self.dispatcher, self._cfg, self._bulbs, self._clock = dispatcher, cfg, bulbs, clock
        self.pulsing: set[str] = set()
        self._last_pulse: dict[str, float] = {}  # bulb -> clock() when its last effect ended
        self._last_state: dict[str, float] = {}  # bulb -> clock() of its last accepted change

    def known(self, name: str) -> None:
        if name not in resolve(self._bulbs):
            raise HTTPException(404, f"unknown bulb {name!r}")

    def ready(self, name: str) -> None:
        self.known(name)
        if name in self.pulsing:
            raise HTTPException(409, "already pulsing")
        cooldown = resolve(self._cfg).web.pulse_cooldown_s
        wait = cooldown - (self._clock() - self._last_pulse.get(name, float("-inf")))
        if wait > 0:
            raise HTTPException(429, f"wait {wait:.0f}s before pulsing again")

    def state_change(self, name: str) -> None:
        """Allow a manual light change now, or raise 404/409/429; records it as made."""
        self.known(name)
        if name in self.pulsing:
            raise HTTPException(409, "an effect is playing on this bulb")
        wait = STATE_MIN_GAP_S - (self._clock() - self._last_state.get(name, float("-inf")))
        if wait > 0:
            raise HTTPException(429, f"wait {wait:.1f}s before changing this bulb again")
        self._last_state[name] = self._clock()

    async def play(self, name: str, pattern: Pattern | SegmentPattern) -> datetime:
        self.pulsing.add(name)
        try:
            return await self.dispatcher.play_now(name, pattern)
        except Exception as e:
            log.warning("pulse check on %s failed: %r", name, e)
            raise HTTPException(502, f"bulb error: {e}") from None
        finally:
            self.pulsing.discard(name)
            self._last_pulse[name] = self._clock()
