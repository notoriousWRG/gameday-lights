"""Offline stand-in for EspnClient that replays recorded scoreboard fixtures."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path


class ReplayClient:
    def __init__(self, directory: str | Path) -> None:
        paths = sorted(Path(directory).glob("*.json.gz"))
        if not paths:
            raise FileNotFoundError(f"no *.json.gz fixtures in {directory}")
        self._frames = [json.loads(gzip.open(p, "rt").read()) for p in paths]
        self._i = 0

    @property
    def start_time(self) -> datetime:
        """Earliest kickoff in the first recorded frame (UTC)."""
        dates = [datetime.fromisoformat(e["date"]) for e in self._frames[0].get("events", [])]
        return min(d.replace(tzinfo=d.tzinfo or UTC) for d in dates)

    @property
    def finished(self) -> bool:
        return self._i >= len(self._frames)

    async def scoreboard(self, league: str, date: str | None = None) -> dict:
        frame = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return frame

    async def team_schedule(
        self, league: str, team_id: str, seasontype: int | None = None
    ) -> dict:
        if seasontype == 3:
            return {"events": []}
        events = []
        for e in self._frames[0].get("events", []):
            comp = e["competitions"][0]
            if any(str(c.get("team", {}).get("id")) == team_id for c in comp["competitors"]):
                events.append({
                    "id": e["id"], "date": e["date"], "shortName": e.get("shortName", ""),
                    "competitions": [{"timeValid": True, "status": e["status"]}],
                })
        return {"events": events}

    async def team(self, league: str, team_id: str) -> dict:
        for e in self._frames[0].get("events", []):
            for c in e["competitions"][0]["competitors"]:
                if str(c.get("team", {}).get("id")) == team_id:
                    return {"team": c["team"]}
        return {"team": {"id": team_id}}

    async def aclose(self) -> None:
        pass
