"""The effects matrix, and the Test actions that play what a team plays on a bulb."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request

from app.bulbs.base import Pattern, SegmentPattern, capabilities_for
from app.config import Config
from app.effects import parse_color
from app.web.common import BulbGuard, color_or_none, iso, require_gameday, resolve
from app.web.data import describe_cell

log = logging.getLogger(__name__)
AnyPattern = Pattern | SegmentPattern


def add_matrix_route(app: FastAPI, cfg: Config | Callable[[], Config]) -> None:
    @app.get("/api/effects/matrix")
    async def effects_matrix() -> dict:
        """Every followed team x the bulbs it uses: the effect it plays there and where each
        setting comes from (default, fixture, team or team x fixture)."""
        config = resolve(cfg)
        by_name = {b.name: b for b in config.bulbs}
        return {
            "bulbs": [{"name": b.name, "segments": b.segments,
                       "kinds": sorted(capabilities_for(b.kind, b.segments).kinds)}
                      for b in config.bulbs],
            "cells": [describe_cell(config, t, by_name[n])
                      for t in config.teams for n in t.bulbs if n in by_name],
        }


def add_test_routes(
    app: FastAPI,
    guard: BulbGuard,
    dry_run: bool,
    cell_pattern: Callable[[str, str, str], AnyPattern] | None,
    team_test: Callable[..., AnyPattern] | None,
) -> None:
    if cell_pattern is not None:

        @app.post("/api/effects/test")
        async def test_cell(request: Request) -> dict:
            """Play what one team plays on one bulb, the saved effect, with the same guards,
            queue and snapshot/restore as the pulse check."""
            require_gameday(request)
            try:
                body = await request.json()
                league, team_id, name = str(body["league"]), str(body["id"]), str(body["bulb"])
            except (ValueError, KeyError, TypeError):
                raise HTTPException(400, 'body must be {"league", "id", "bulb"}') from None
            guard.ready(name)
            try:
                pattern = cell_pattern(league, team_id, name)
            except KeyError:
                raise HTTPException(404, "that team does not use that bulb") from None
            except ValueError as e:
                raise HTTPException(422, f"cannot build that effect: {e}") from None
            started = await guard.play(name, pattern)
            log.info("effect test %s/%s on %s (%.1fs)", league, team_id, name, pattern.duration_s)
            return {"ok": True, "dry_run": dry_run, "duration_s": pattern.duration_s,
                    "started_at": iso(started)}

    if team_test is not None:

        @app.post("/api/teams/test")
        async def test_team(request: Request) -> dict:
            """Play what a team plays on each given bulb (its real per-bulb effect), with the
            colors as edited, saved or not. Same guards, queue and restore as the pulse check;
            one bulb failing does not stop the others."""
            require_gameday(request)
            try:
                body = await request.json()
                league, team_id = str(body["league"]), str(body["id"])
                names = body["bulbs"]
                if not isinstance(names, list) or not names or not all(
                        isinstance(n, str) for n in names):
                    raise ValueError
                color = color_or_none(body.get("color"))
                alt = color_or_none(body.get("alt_color"))
                espn = None
                if body.get("espn_color") and body.get("espn_alt_color"):
                    espn = (parse_color(body["espn_color"]), parse_color(body["espn_alt_color"]))
            except (ValueError, KeyError, TypeError):
                raise HTTPException(
                    400, 'body must be {"league", "id", "bulbs": [names], optional colors as '
                         '"#rrggbb"}') from None
            names = list(dict.fromkeys(names))
            for n in names:
                guard.ready(n)
            try:
                patterns = {n: team_test(league, team_id, n, color, alt, espn) for n in names}
            except ValueError as e:
                raise HTTPException(422, f"cannot build that effect: {e}") from None
            results = await asyncio.gather(
                *(guard.play(n, patterns[n]) for n in names), return_exceptions=True)
            out = [{"name": n, "ok": not isinstance(r, BaseException),
                    "error": str(getattr(r, "detail", r)) if isinstance(r, BaseException)
                    else None} for n, r in zip(names, results, strict=True)]
            started = [r for r in results if isinstance(r, datetime)]
            if not started:
                raise HTTPException(502, "; ".join(f"{o['name']}: {o['error']}" for o in out))
            took = max(patterns[o["name"]].duration_s for o in out if o["ok"])
            log.info("team test %s/%s on %s (%.1fs)", league, team_id, ", ".join(names), took)
            return {"ok": all(o["ok"] for o in out), "dry_run": dry_run, "duration_s": took,
                    "bulbs": out, "started_at": iso(min(started))}
