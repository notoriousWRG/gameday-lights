"""Diagnostics: what a household would text to the person who set it up. Read-only, and never
carries a secret (signing keys, passwords, URLs with tokens): only whether one is set."""

from __future__ import annotations

import platform
from collections.abc import Awaitable, Callable
from datetime import datetime
from importlib import metadata
from pathlib import Path

from fastapi import FastAPI

from app.config import Config
from app.store import Store
from app.watcher import WatcherStats
from app.web.common import iso, resolve


def app_version() -> str:
    try:
        return metadata.version("gameday-lights")
    except metadata.PackageNotFoundError:
        return "dev"


def build_diagnostics(
    store: Store,
    cfg: Config,
    stats: WatcherStats,
    pings: dict[str, float | None],
    dry_run: bool,
    now: datetime,
    practice_on: bool = False,
    config_path: Path | None = None,
) -> dict:
    events = store.recent_events(1)
    last_event = None
    if events:
        e = events[0]
        game = store.get_game(e.game_id)
        last_event = {
            "game": game.name if game else e.game_id,
            "label": e.detail.get("label", e.type),
            "status": e.status,
            "detected_at": iso(e.detected_at),
            "fired_at": iso(e.fired_at),
        }
    started = stats.started_at
    data = {
        "version": app_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "now": iso(now),
        "uptime_s": round((now - started).total_seconds()) if started else None,
        "mode": "dry_run" if dry_run else "live",
        "practice": practice_on,
        "config_path": str(config_path) if config_path else None,
        "db_path": str(cfg.general.db_path),
        "teams": [t.abbr for t in cfg.teams],
        "notifier": cfg.health.notify,
        "heartbeat_set": bool(cfg.health.heartbeat_url),  # whether, never the URL itself
        "bulbs": [
            {"name": b.name, "kind": b.kind, "ip": b.ip, "reachable": pings.get(b.name) is not None,
             "ping_ms": None if pings.get(b.name) is None else round(pings[b.name] * 1000)}
            for b in cfg.bulbs
        ],
        "watcher": {
            "last_poll_at": iso(stats.last_poll_at),
            "last_ok_at": iso(stats.last_ok_at),
            "polls": stats.polls,
            "errors": stats.errors,
            "last_error": stats.last_error,
            "watching": stats.watching,
        },
        "last_event": last_event,
    }
    data["bundle"] = bundle_text(data)
    return data


def bundle_text(d: dict) -> str:
    """The same facts as a few lines of plain text, short enough for a text message."""
    w = d["watcher"]
    lines = [
        f"Gameday Lights {d['version']} ({d['mode']}{', practice' if d['practice'] else ''})",
        f"{d['platform']}, Python {d['python']}",
        f"up {d['uptime_s']}s; teams: {', '.join(d['teams']) or 'none'}",
        f"ESPN: last ok {w['last_ok_at'] or 'never'}; {w['errors']} errors"
        + (f"; last: {w['last_error']}" if w["last_error"] else ""),
    ]
    for b in d["bulbs"]:
        state = f"{b['ping_ms']} ms" if b["reachable"] else "NOT answering"
        lines.append(f"bulb {b['name']} ({b['kind']} {b['ip']}): {state}")
    if not d["bulbs"]:
        lines.append("no bulbs added")
    e = d["last_event"]
    lines.append(f"last event: {e['game']} {e['label']} {e['status']} {e['detected_at']}"
                 if e else "last event: none yet")
    return "\n".join(lines)


def add_diagnostics_routes(
    app: FastAPI,
    store: Store,
    cfg: Config | Callable[[], Config],
    stats: WatcherStats,
    get_pings: Callable[[], Awaitable[dict[str, float | None]]],
    dry_run: bool,
    now: Callable[[], datetime],
    practice=None,
    config_path: Path | None = None,
) -> None:
    @app.get("/api/diagnostics")
    async def diagnostics() -> dict:
        on = practice is not None and practice.practice_active()
        return build_diagnostics(store, resolve(cfg), stats, await get_pings(), dry_run, now(),
                                 on, config_path)
