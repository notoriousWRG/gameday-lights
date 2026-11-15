"""Status page: GET / (HTML) and GET /api/status (JSON). The other routes live in the
routes_* modules; `create_app` wires them together. Writes are guarded: see `common.py`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response

from app.bulbs.base import BulbAdapter, Pattern, SegmentPattern
from app.config import Config
from app.dispatch.dispatcher import Dispatcher, utc_now
from app.espn.client import EspnClient
from app.settings_service import SettingsService
from app.store import Store
from app.watcher import WatcherStats
from app.web.common import BulbGuard, resolve
from app.web.data import (  # noqa: F401  (re-exported: other modules and tests import them here)
    build_status,
    describe_cell,
    schedule_rows,
    scoreboard_card,
    setup_items,
    team_entries,
    team_key,
)
from app.web.routes_bulbs import add_bulb_routes, add_discover_route
from app.web.routes_calibration import add_calibration_routes
from app.web.routes_diagnostics import add_diagnostics_routes
from app.web.routes_effects import add_matrix_route, add_test_routes
from app.web.routes_settings import add_settings_routes
from app.web.routes_teams import add_team_routes

log = logging.getLogger(__name__)

PAGE = Path(__file__).with_name("status.html")
ASSET_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
PING_TTL_S = 30.0
PING_TIMEOUT_S = 3.0


class BulbPings:
    """Cached reachability checks, so refreshing the page never hammers the bulb."""

    def __init__(
        self,
        bulbs: dict[str, BulbAdapter] | Callable[[], dict[str, BulbAdapter]],
        clock: Callable[[], float] = time.monotonic,
    ):
        self._bulbs, self._clock = bulbs, clock
        self._at = float("-inf")
        self._last: dict[str, float | None] = {}

    async def get(self) -> dict[str, float | None]:
        bulbs = resolve(self._bulbs)
        fresh = self._clock() - self._at < PING_TTL_S
        if fresh and set(bulbs) == set(self._last):  # a bulb added or removed refreshes at once
            return self._last

        async def one(b: BulbAdapter) -> float | None:
            try:
                return await asyncio.wait_for(b.ping(), PING_TIMEOUT_S)
            except Exception:
                return None

        names = list(bulbs)
        results = await asyncio.gather(*(one(bulbs[n]) for n in names))
        self._last = dict(zip(names, results, strict=True))
        self._at = self._clock()
        return self._last


def create_app(
    store: Store,
    cfg: Config | Callable[[], Config],
    stats: WatcherStats,
    bulbs: dict[str, BulbAdapter] | Callable[[], dict[str, BulbAdapter]],
    dry_run: bool,
    now: Callable[[], datetime] = utc_now,
    dispatcher: Dispatcher | None = None,
    pulse_pattern: Callable[[str], Pattern | SegmentPattern] | None = None,
    clock: Callable[[], float] = time.monotonic,
    settings: SettingsService | None = None,
    espn: EspnClient | None = None,
    discover_bulbs: Callable[[], Awaitable[list[dict]]] | None = None,
    team_test: Callable[..., Pattern | SegmentPattern] | None = None,
    cell_pattern: Callable[[str, str, str], Pattern | SegmentPattern] | None = None,
    practice=None,
    config_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Gameday Lights status", docs_url=None, redoc_url=None, openapi_url=None)
    pings = BulbPings(bulbs)
    # Read the page and its scripts once, at startup: they must come from the same version as
    # this API. (Reading per request let an updated page meet a not-yet-restarted server.)
    page = PAGE.read_text(encoding="utf-8")
    static = PAGE.parent / "static"
    files = sorted(static.iterdir()) if static.is_dir() else []
    assets = {f.name: (f.read_text(encoding="utf-8"), ASSET_TYPES[f.suffix])
              for f in files if f.suffix in ASSET_TYPES}

    # async handlers only: the sqlite connection belongs to the event loop thread
    @app.get("/api/setup")
    async def setup() -> dict:
        return {"items": setup_items(resolve(cfg), await pings.get(), dry_run)}

    @app.get("/api/status")
    async def status() -> dict:
        return build_status(store, resolve(cfg), stats, await pings.get(), dry_run, now())

    add_diagnostics_routes(app, store, cfg, stats, pings.get, dry_run, now, practice, config_path)
    add_matrix_route(app, cfg)
    add_calibration_routes(app, store, cfg, now, practice)
    if dispatcher is not None and pulse_pattern is not None:
        guard = BulbGuard(dispatcher, cfg, bulbs, clock)
        add_bulb_routes(app, guard, pulse_pattern, dry_run)
        add_test_routes(app, guard, dry_run, cell_pattern, team_test)
    if settings is not None:
        add_settings_routes(app, settings)
    if espn is not None:
        add_team_routes(app, espn, cfg)
    if discover_bulbs is not None:
        add_discover_route(app, discover_bulbs, cfg)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return page

    @app.get("/static/{name}")
    async def static_file(name: str) -> Response:
        if name not in assets:
            raise HTTPException(404, "no such file")
        text, media_type = assets[name]
        return Response(text, media_type=media_type, headers={"Cache-Control": "no-cache"})

    return app


class _Server(uvicorn.Server):
    """uvicorn without its own SIGINT/SIGTERM handlers: the CLI owns shutdown."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield

async def _run(server: uvicorn.Server) -> None:
    try:
        await server.serve()
    except SystemExit as e:  # uvicorn exits on a bind failure; keep that inside the task
        raise OSError(f"uvicorn exited ({e.code})") from None

async def serve_status(app: FastAPI, host: str, port: int) -> None:
    """Run the page until cancelled. A bind failure is logged; it never stops the watcher."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warning("status page listening on %s:%d with no login; keep it on your home network",
                    host, port)
    server = _Server(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                    access_log=False))
    task = asyncio.ensure_future(_run(server))
    try:
        log.info("status page: http://%s:%d/", host, port)
        await asyncio.shield(task)
    except asyncio.CancelledError:
        server.should_exit = True  # graceful stop; a hard cancel makes uvicorn log a traceback
        try:
            await asyncio.wait_for(task, 5)
        except (TimeoutError, asyncio.CancelledError, OSError):
            pass
        raise
    except OSError as e:
        log.error("status page could not start on %s:%d (%s); continuing without it",
                  host, port, e)
