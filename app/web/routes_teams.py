"""Looking up teams to follow (ESPN's team lists)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException

from app.espn.client import LEAGUES, EspnError
from app.espn.schedule import parse_team_list
from app.web.common import resolve

log = logging.getLogger(__name__)


def add_team_routes(app: FastAPI, espn, cfg) -> None:
    """Find teams to follow: ESPN's team list (cached 24 h by the client), with colors."""
    labels = {"nfl": "NFL", "nhl": "NHL"}

    @app.get("/api/leagues")
    async def leagues() -> list[dict]:
        return [{"key": k, "label": labels.get(k, k.upper())} for k in LEAGUES]

    @app.get("/api/teams/search")
    async def search_teams(league: str, q: str = "") -> list[dict]:
        if league not in LEAGUES:
            raise HTTPException(400, f"unknown league {league!r}")
        try:
            teams = parse_team_list(await espn.teams(league))
        except EspnError as e:
            raise HTTPException(502, f"ESPN is not answering: {e}") from None
        words = q.lower().split()
        followed = {(t.league, t.id) for t in resolve(cfg).teams}
        found = [
            {**t, "league": league, "followed": (league, t["id"]) in followed}
            for t in teams
            if all(w in f"{t['name']} {t['abbr']}".lower() for w in words)
        ]
        return found[:50]
