"""The only ESPN caller: httpx async, TTL cache, timeout, exponential backoff."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

SITE = "https://site.api.espn.com/apis/site/v2/sports"
LEAGUES = {"nfl": "football/nfl", "nhl": "hockey/nhl"}
SCOREBOARD_TTL_S = 10.0  # also the floor: never poll a live scoreboard faster than this
SCHEDULE_TTL_S = 3600.0
TEAMS_TTL_S = 86400.0


class EspnError(RuntimeError):
    pass


def _sport_path(league: str) -> str:
    if league in LEAGUES:
        return LEAGUES[league]
    if league.count("/") == 1 and all(league.split("/")):
        return league
    raise EspnError(f"unknown league {league!r}; use nfl, nhl or 'sport/league'")


class EspnClient:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout_s: float = 10.0,
        retries: int = 3,
        backoff_s: float = 1.0,
    ) -> None:
        self._http = httpx.AsyncClient(transport=transport, timeout=timeout_s)
        self._clock = clock
        self._sleep = sleep
        self._retries = retries
        self._backoff_s = backoff_s
        self._cache: dict[tuple, tuple[float, Any]] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def scoreboard(self, league: str, date: str | None = None) -> dict:
        params = {"dates": date} if date else {}
        return await self._get(f"{SITE}/{_sport_path(league)}/scoreboard", params, SCOREBOARD_TTL_S)

    async def team_schedule(
        self, league: str, team_id: str, seasontype: int | None = None
    ) -> dict:
        params = {"seasontype": seasontype} if seasontype else {}
        url = f"{SITE}/{_sport_path(league)}/teams/{team_id}/schedule"
        return await self._get(url, params, SCHEDULE_TTL_S)

    async def teams(self, league: str) -> dict:
        return await self._get(f"{SITE}/{_sport_path(league)}/teams", {}, TEAMS_TTL_S)

    async def team(self, league: str, team_id: str) -> dict:
        return await self._get(f"{SITE}/{_sport_path(league)}/teams/{team_id}", {}, TEAMS_TTL_S)

    async def _get(self, url: str, params: dict, ttl_s: float) -> dict:
        key = (url, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        now = self._clock()
        if hit and now - hit[0] < ttl_s:
            return hit[1]

        last = "no attempt made"
        for attempt in range(self._retries + 1):
            try:
                r = await self._http.get(url, params=params)
            except httpx.TransportError as e:
                last = f"{type(e).__name__}: {e}"
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"HTTP {r.status_code}"
                elif r.status_code >= 400:
                    raise EspnError(f"HTTP {r.status_code} from {url}")
                else:
                    try:
                        data = r.json()
                    except ValueError as e:
                        raise EspnError(f"invalid JSON from {url}: {e}") from None
                    self._cache[key] = (self._clock(), data)
                    return data
            if attempt < self._retries:
                delay = self._backoff_s * 2**attempt
                log.warning("ESPN %s failed (%s); retrying in %.1fs", url, last, delay)
                await self._sleep(delay)
        raise EspnError(f"{url} failed after {self._retries + 1} attempts: {last}")
