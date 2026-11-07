"""Status page: GET / (HTML) and GET /api/status (JSON), plus one guarded write action:
POST /api/bulbs/{name}/pulse (the pulse check)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.bulbs.base import BulbAdapter, Pattern
from app.config import Config, ConfigError
from app.dispatch.dispatcher import Dispatcher, utc_now
from app.effects import parse_color
from app.espn.client import LEAGUES, EspnClient, EspnError
from app.espn.schedule import parse_team_list
from app.settings import SECTIONS, error_location
from app.settings_service import SettingsService
from app.store import RevisionConflict, Store
from app.watcher import WatcherStats

log = logging.getLogger(__name__)

PAGE = Path(__file__).with_name("status.html")
PING_TTL_S = 30.0
PING_TIMEOUT_S = 3.0


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _color_or_none(value):
    """"#rrggbb" -> a color, null or "" -> None; anything else is a ValueError (a 400)."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("color must be text")
    return parse_color(value)


def _resolve(value):
    """A value, or a function returning the current one (settings edits apply live)."""
    return value() if callable(value) else value


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
        bulbs = _resolve(self._bulbs)
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


def team_key(league: str, abbr: str) -> str:
    return f"{league}:{abbr.upper()}"


def team_entries(cfg: Config) -> list[dict]:
    """Followed teams with a stable key, a label that is unambiguous, and the configured color."""
    counts: dict[str, int] = {}
    for t in cfg.teams:
        counts[t.abbr.upper()] = counts.get(t.abbr.upper(), 0) + 1
    out = []
    for t in cfg.teams:
        ambiguous = counts[t.abbr.upper()] > 1  # e.g. PIT in the NFL and the NHL
        color = "#{:02x}{:02x}{:02x}".format(*t.color) if t.color else None
        out.append({
            "league": t.league, "abbr": t.abbr, "bulbs": list(t.bulbs),
            "key": team_key(t.league, t.abbr),
            "label": f"{t.abbr} · {t.league.upper()}" if ambiguous else t.abbr,
            "color": color,
        })
    return out


def schedule_rows(store: Store, cfg: Config) -> list[dict]:
    """Every stored game in order, one row per followed team in it, from that team's side
    (us vs opp, W/L when final). Two followed teams in one game get a row on each schedule."""
    followed = {team_key(t.league, t.abbr) for t in cfg.teams}
    order = {team_key(t.league, t.abbr): i for i, t in enumerate(cfg.teams)}
    rows = []
    for g in store.all_games():
        sides = {"home": (g.home_abbr, g.home_score), "away": (g.away_abbr, g.away_score)}
        base = {"id": g.game_id, "name": g.name, "start_utc": _iso(g.start_utc),
                "status": g.status, "league": g.league, "team_key": None, "us": None,
                "opp": None, "home": None, "us_score": None, "opp_score": None, "result": None}
        mine = [
            (side, other) for side, other in (("home", "away"), ("away", "home"))
            if sides[side][0] and team_key(g.league, sides[side][0]) in followed
        ]
        if not mine:
            if not (g.home_abbr or g.away_abbr):
                rows.append(base)  # no team data yet (a legacy row); shown under "All teams" only
            continue  # else: a game of a team that is no longer followed
        mine.sort(key=lambda m: order[team_key(g.league, sides[m[0]][0])])
        for side, other in mine:
            row = dict(base)
            row.update(team_key=team_key(g.league, sides[side][0]), us=sides[side][0],
                       opp=sides[other][0], home=side == "home", us_score=sides[side][1],
                       opp_score=sides[other][1])
            if g.status == "post" and row["us_score"] is not None and row["opp_score"] is not None:
                diff = row["us_score"] - row["opp_score"]
                row["result"] = "W" if diff > 0 else "L" if diff < 0 else "T"
            rows.append(row)
    return rows


THIS_WEEK = timedelta(days=7)
MAX_NEXT_GAMES = 3  # how many followed teams' next games the Scoreboard shows at once


def _scoreboard_game(store: Store, live: dict, followed: set[str]) -> dict:
    game = store.get_game(live["game_id"])

    def side(s: dict) -> dict:
        us = bool(game and s["abbr"] and team_key(game.league, s["abbr"]) in followed)
        return {**s, "us": us}

    return {
        "id": live["game_id"],
        "league": game.league if game else None,
        "name": live["name"],
        "start_utc": _iso(game.start_utc) if game else None,
        "state": live["state"],
        "status_name": live["status_name"],
        "detail": live["detail"],
        "clock": live["clock"],
        "period": live["period"],
        "home": side(live["home"]),
        "away": side(live["away"]),
        "broadcast": live["broadcast"],
        "venue": live["venue"],
        "situation": live["situation"],
        "updated_at": _iso(live["updated_at"]),
        "ended_at": _iso(live["ended_at"]),
    }


def scoreboard_card(
    store: Store, cfg: Config, stats: WatcherStats, now: datetime, schedule: list[dict]
) -> dict:
    """What the Scoreboard card shows: games in their window (live/pre), a game that just
    finished (for `final_hold_min`), or else the next game of each followed team (at most
    MAX_NEXT_GAMES)."""
    followed = {team_key(t.league, t.abbr) for t in cfg.teams}
    hold = timedelta(minutes=cfg.web.final_hold_min)
    games = []
    for gid, live in stats.live.items():
        active = gid in stats.watching_ids and live["state"] in ("pre", "in")
        just_finished = (
            live["state"] == "post" and live["ended_at"] is not None
            and now - live["ended_at"] <= hold
        )
        if active or just_finished:
            games.append(_scoreboard_game(store, live, followed))
    games.sort(key=lambda g: (g["state"] != "in", g["start_utc"] or ""))
    states = {g["state"] for g in games}
    shown = {g["id"] for g in games}
    # "Next" means not started: a game already in progress without live data yet is not next.
    # One per followed team (its first such game), soonest first; a game two followed teams
    # share is one card, kept on the team that comes first in the list (schedule is in that order).
    first_per_team: dict[str, dict] = {}
    for r in schedule:
        if r["status"] == "pre" and r["id"] not in shown:
            first_per_team.setdefault(r["team_key"] or "", r)
    next_games, seen = [], set()
    for r in sorted(first_per_team.values(), key=lambda r: r["start_utc"]):
        if r["id"] not in seen:
            seen.add(r["id"])
            in_week = datetime.fromisoformat(r["start_utc"]) - now <= THIS_WEEK
            next_games.append({**r, "in_week": in_week})
    next_games = next_games[:MAX_NEXT_GAMES]
    if "in" in states:
        mode = "live"
    elif "pre" in states:
        mode = "pre"
    elif games:
        mode = "final"
    else:
        mode = "next" if next_games else "idle"
    return {
        "mode": mode,
        "polling": {
            "active": bool(stats.watching_ids),
            "interval_s": stats.poll_interval_s,
            "last_poll_at": _iso(stats.last_poll_at),
            "lead_min": cfg.general.watch_lead_min,
        },
        "games": games,
        "next_games": next_games,
    }


def build_status(
    store: Store,
    cfg: Config,
    stats: WatcherStats,
    pings: dict[str, float | None],
    dry_run: bool,
    now: datetime,
) -> dict:
    events = []
    for e in store.recent_events(25):
        game = store.get_game(e.game_id)
        events.append({
            "key": e.dedupe_key,
            "game": game.name if game else e.game_id,
            "team": e.detail.get("abbr", e.team_id),
            "label": e.detail.get("label", e.type),
            "delta": e.detail.get("delta"),
            "status": e.status,
            "detected_at": _iso(e.detected_at),
            "due_at": _iso(e.due_at),
            "fired_at": _iso(e.fired_at),
            "fire_delay_s": (e.fired_at - e.detected_at).total_seconds() if e.fired_at else None,
        })
    schedule = schedule_rows(store, cfg)
    try:
        version = metadata.version("gameday-lights")
    except metadata.PackageNotFoundError:
        version = "dev"
    started = stats.started_at
    return {
        "version": version,
        "now": _iso(now),
        "uptime_s": (now - started).total_seconds() if started else None,
        "mode": "dry_run" if dry_run else "live",
        "delay_s": cfg.general.delay_s,
        "teams": team_entries(cfg),
        "bulbs": [
            {"name": b.name, "ip": b.ip,
             "ping_ms": None if pings.get(b.name) is None else round(pings[b.name] * 1000)}
            for b in cfg.bulbs
        ],
        "watcher": {
            "last_sync_at": _iso(stats.last_sync_at),
            "last_poll_at": _iso(stats.last_poll_at),
            "last_ok_at": _iso(stats.last_ok_at),
            "polls": stats.polls,
            "errors": stats.errors,
            "last_error": stats.last_error,
            "watching": stats.watching,
        },
        "schedule": schedule,
        "scoreboard": scoreboard_card(store, cfg, stats, now, schedule),
        "events": events,
    }


def create_app(
    store: Store,
    cfg: Config | Callable[[], Config],
    stats: WatcherStats,
    bulbs: dict[str, BulbAdapter] | Callable[[], dict[str, BulbAdapter]],
    dry_run: bool,
    now: Callable[[], datetime] = utc_now,
    dispatcher: Dispatcher | None = None,
    pulse_pattern: Callable[[str], Pattern] | None = None,
    clock: Callable[[], float] = time.monotonic,
    settings: SettingsService | None = None,
    espn: EspnClient | None = None,
    discover_bulbs: Callable[[], Awaitable[list[dict]]] | None = None,
    team_pulse: Callable[..., Pattern] | None = None,
) -> FastAPI:
    app = FastAPI(title="Gameday Lights status", docs_url=None, redoc_url=None, openapi_url=None)
    pings = BulbPings(bulbs)
    # Read the page once, at startup: it must come from the same version as this API.
    # (Reading per request let an updated page meet a not-yet-restarted server.)
    page = PAGE.read_text(encoding="utf-8")
    pulsing: set[str] = set()
    last_pulse: dict[str, float] = {}  # bulb -> clock() when its last pulse ended

    # async handlers only: the sqlite connection belongs to the event loop thread
    @app.get("/api/status")
    async def status() -> dict:
        return build_status(store, _resolve(cfg), stats, await pings.get(), dry_run, now())

    if dispatcher is not None and pulse_pattern is not None:

        def ready(name: str) -> None:
            if name not in _resolve(bulbs):
                raise HTTPException(404, f"unknown bulb {name!r}")
            if name in pulsing:
                raise HTTPException(409, "already pulsing")
            cooldown = _resolve(cfg).web.pulse_cooldown_s
            wait = cooldown - (clock() - last_pulse.get(name, float("-inf")))
            if wait > 0:
                raise HTTPException(429, f"wait {wait:.0f}s before pulsing again")

        async def play(name: str, pattern: Pattern) -> datetime:
            pulsing.add(name)
            try:
                return await dispatcher.play_now(name, pattern)
            except Exception as e:
                log.warning("pulse check on %s failed: %r", name, e)
                raise HTTPException(502, f"bulb error: {e}") from None
            finally:
                pulsing.discard(name)
                last_pulse[name] = clock()

        @app.post("/api/bulbs/{name}/pulse")
        async def pulse(name: str, request: Request) -> dict:
            # The one write action. A cross-site form post cannot set a custom header
            # without a CORS preflight, which this app never answers.
            if request.headers.get("x-gameday") != "1":
                raise HTTPException(403, "missing X-Gameday header")
            ready(name)
            pattern = pulse_pattern(name)
            started = await play(name, pattern)
            log.info("pulse check on %s (%.1fs)", name, pattern.duration_s)
            return {"ok": True, "dry_run": dry_run, "duration_s": pattern.duration_s,
                    "started_at": _iso(started)}

        if team_pulse is not None:

            @app.post("/api/teams/test")
            async def test_team(request: Request) -> dict:
                """Play a team's score effect, with the colors as edited (saved or not), on the
                bulbs given. Same guards, queue and snapshot/restore as the pulse check."""
                if request.headers.get("x-gameday") != "1":
                    raise HTTPException(403, "missing X-Gameday header")
                try:
                    body = await request.json()
                    league, team_id = str(body["league"]), str(body["id"])
                    names = body["bulbs"]
                    if not isinstance(names, list) or not names or not all(
                            isinstance(n, str) for n in names):
                        raise ValueError
                    color = _color_or_none(body.get("color"))
                    alt = _color_or_none(body.get("alt_color"))
                    espn = None
                    if body.get("espn_color") and body.get("espn_alt_color"):
                        espn = (parse_color(body["espn_color"]),
                                parse_color(body["espn_alt_color"]))
                except (ValueError, KeyError, TypeError):
                    raise HTTPException(
                        400, 'body must be {"league", "id", "bulbs": [names], optional colors as '
                             '"#rrggbb"}') from None
                names = list(dict.fromkeys(names))
                for n in names:
                    ready(n)
                pattern = team_pulse(league, team_id, color, alt, espn)
                started = await asyncio.gather(*(play(n, pattern) for n in names))
                log.info("team test %s/%s on %s (%.1fs)", league, team_id, ", ".join(names),
                         pattern.duration_s)
                return {"ok": True, "dry_run": dry_run, "duration_s": pattern.duration_s,
                        "bulbs": names, "started_at": _iso(min(started))}

    if settings is not None:
        _add_settings_routes(app, settings)
    if espn is not None:
        _add_team_routes(app, espn, cfg)
    if discover_bulbs is not None:
        _add_discover_route(app, discover_bulbs, cfg)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return page

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


def _error_item(message: str) -> dict:
    """A ConfigError message looks like "teams[0].bulbs: unknown bulb 'x'": split the path from
    the text and say which section's editor the field belongs to."""
    path, sep, text = message.partition(": ")
    if not sep:
        return {"section": "", "path": "", "message": message}
    section, field = error_location(path)
    return {"section": section, "path": field, "message": text}


def _parse_if_match(value: str | None) -> int:
    if value is None:
        raise HTTPException(428, "If-Match: <revision> is required")
    try:
        return int(value.strip().removeprefix("W/").strip('"'))
    except ValueError:
        raise HTTPException(400, "If-Match must be the revision number you loaded") from None


def _add_settings_routes(app: FastAPI, settings: SettingsService) -> None:
    """Read and edit stored settings. Writes need X-Gameday (cross-site posts cannot send it) and
    If-Match (so two editors cannot silently overwrite each other)."""

    def machine() -> dict:
        cfg = settings.config
        return {"dispatch_enabled": cfg.general.dispatch_enabled,
                "db_path": str(cfg.general.db_path),
                "web": {"enabled": cfg.web.enabled, "host": cfg.web.host, "port": cfg.web.port},
                "editable": False}  # these live in config.toml only

    @app.get("/api/settings")
    async def get_settings() -> dict:
        return {"sections": settings.public_sections(), "machine": machine()}

    @app.get("/api/settings/history")
    async def get_history(limit: int = 50, section: str | None = None) -> list[dict]:
        return settings.history(max(1, min(limit, 500)), section)

    @app.post("/api/bulbs/{name}/rename")
    async def rename_bulb(name: str, request: Request):
        """Rename a bulb together with the teams that use it (they refer to it by name)."""
        if request.headers.get("x-gameday") != "1":
            raise HTTPException(403, "missing X-Gameday header")
        try:
            body = await request.json()
            to, revs = body["to"], body["revisions"]
            bulbs_rev, teams_rev = int(revs["bulbs"]), int(revs["teams"])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(
                400, 'body must be {"to": name, "revisions": {"bulbs": n, "teams": n}}'
            ) from None
        if not isinstance(to, str):
            raise HTTPException(400, '"to" must be text')
        try:
            settings.rename_bulb(name, to, bulbs_rev, teams_rev, source="ui")
        except ConfigError as e:
            return JSONResponse({"errors": [_error_item(str(e))]}, status_code=422)
        except RevisionConflict as e:
            return JSONResponse({"detail": str(e), "current_revision": e.current_revision},
                                status_code=409)
        log.info("settings: bulb %r renamed to %r", name, to.strip())
        return {"ok": True, "sections": settings.public_sections()}

    @app.put("/api/settings/{section}")
    async def put_settings(section: str, request: Request):
        if request.headers.get("x-gameday") != "1":
            raise HTTPException(403, "missing X-Gameday header")
        if section not in SECTIONS:
            raise HTTPException(404, f"unknown settings section {section!r}")
        expected = _parse_if_match(request.headers.get("if-match"))
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        if not isinstance(body, dict) or "value" not in body:
            raise HTTPException(400, 'body must be {"value": ...}')
        try:
            revision, _ = settings.update(section, body["value"], expected, source="ui")
        except ConfigError as e:
            return JSONResponse({"errors": [_error_item(str(e))]}, status_code=422)
        except RevisionConflict as e:
            current = settings.public_sections().get(section, {})
            return JSONResponse(
                {"detail": str(e), "current_revision": e.current_revision,
                 "value": current.get("value")}, status_code=409)
        log.info("settings: %s saved (revision %d)", section, revision)
        value = settings.public_sections()[section]["value"]
        return {"revision": revision, "value": value, "applied": True}


def _add_team_routes(app: FastAPI, espn, cfg) -> None:
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
        followed = {(t.league, t.id) for t in _resolve(cfg).teams}
        found = [
            {**t, "league": league, "followed": (league, t["id"]) in followed}
            for t in teams
            if all(w in f"{t['name']} {t['abbr']}".lower() for w in words)
        ]
        return found[:50]


def _add_discover_route(app: FastAPI, discover_bulbs, cfg) -> None:
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
        stored = _resolve(cfg).bulbs
        out = []
        for b in found:
            def norm(m):
                return (m or "").lower().replace(":", "")

            match = next((s for s in stored if (s.mac and norm(s.mac) == b["mac"])
                          or (not s.mac and s.ip == b["ip"])), None)
            out.append({"ip": b["ip"], "mac": b["mac"], "known": match is not None,
                        "name": match.name if match else None})
        return out


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
