"""Delay calibration: say when a score showed on the TV, and see what the delay should be."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request

from app.config import Config
from app.dispatch.dispatcher import utc_now
from app.store import Store
from app.web.common import iso, require_gameday, resolve
from app.web.data import calibration

log = logging.getLogger(__name__)


def add_calibration_routes(
    app: FastAPI,
    store: Store,
    cfg: Config | Callable[[], Config],
    now: Callable[[], datetime] = utc_now,
    practice=None,
) -> None:
    """`practice` is the watcher (or anything with its practice methods); without one, practice
    mode reads as off and cannot be started."""

    @app.get("/api/calibration")
    async def get_calibration() -> dict:
        return calibration(store, resolve(cfg), now=now())

    def practice_state() -> dict:
        active = practice is not None and practice.practice_active()
        return {"active": active, "until": iso(practice.practice_until) if active else None,
                "minutes": resolve(cfg).web.practice_minutes,
                "available": practice is not None and practice.can_practice()}

    @app.get("/api/practice")
    async def get_practice() -> dict:
        return practice_state()

    @app.put("/api/practice")
    async def put_practice(request: Request) -> dict:
        """Turn practice mode on (for `web.practice_minutes`) or off. A restart leaves it off."""
        require_gameday(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("active"), bool):
            raise HTTPException(400, 'body must be {"active": true or false}')
        if practice is None:
            raise HTTPException(409, "practice mode is not available here")
        if body["active"]:
            if not practice.can_practice():
                raise HTTPException(409, "no game to practice on yet: it starts when a followed "
                                         "game is about to begin")
            practice.start_practice(resolve(cfg).web.practice_minutes)
            log.info("practice mode on until %s", practice.practice_until)
        else:
            practice.stop_practice()
            log.info("practice mode off")
        return practice_state()

    @app.post("/api/events/{key}/seen")
    async def mark_seen(key: str, request: Request) -> dict:
        """Stamp the event with the server's clock now: the moment someone says it showed on TV."""
        require_gameday(request)
        when = now()
        event = store.get_event(key)
        if event is None:
            raise HTTPException(404, "no such event")
        limit_min = resolve(cfg).web.mark_window_min
        if (when - event.detected_at).total_seconds() > limit_min * 60:
            raise HTTPException(
                409, f"too late to mark this one: it showed more than {limit_min:g} minutes ago, "
                     "which says little about the delay")
        store.mark_seen(key, when)
        event = store.get_event(key)
        log.info("calibration: %s seen on TV %.1fs after detection", key, event.lag_s)
        return {"ok": True, "seen_at": iso(when), "lag_s": round(event.lag_s, 1)}

    @app.delete("/api/events/{key}/seen")
    async def clear_seen(key: str, request: Request) -> dict:
        require_gameday(request)
        if not store.mark_seen(key, None):
            raise HTTPException(404, "no such event")
        return {"ok": True}
