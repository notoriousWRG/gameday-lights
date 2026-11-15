"""Health alerts that leave the house. The heartbeat is a plain GET on a schedule: an outside
monitor emails the owner when the pings stop (a crash, power loss or no internet cannot report
itself). With no URL set nothing is ever sent."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import Config

log = logging.getLogger(__name__)
TIMEOUT_S = 10.0


async def ping_once(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(url, timeout=TIMEOUT_S)
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.debug("heartbeat failed: %r", e)
        return False


async def run_heartbeat(
    config: Callable[[], Config],
    transport: httpx.AsyncBaseTransport | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Ping `health.heartbeat_url` every `heartbeat_interval_s` until cancelled. The config is
    read each round, so the URL and interval follow edits to the file's machine settings on
    restart. A failure is logged once when it starts and once when it clears, not every try."""
    failing = False
    async with httpx.AsyncClient(transport=transport) as client:
        while True:
            health = config().health
            if health.heartbeat_url:
                ok = await ping_once(client, health.heartbeat_url)
                if not ok and not failing:
                    log.warning("heartbeat is failing (monitor unreachable); will keep trying")
                elif ok and failing:
                    log.info("heartbeat is back")
                failing = not ok
            await sleep(health.heartbeat_interval_s)
