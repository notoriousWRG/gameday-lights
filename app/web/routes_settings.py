"""Read and edit the stored settings, and rename a bulb together with the teams that use it."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import ConfigError
from app.settings import SECTIONS
from app.settings_service import SettingsService
from app.store import RevisionConflict
from app.web.common import error_item, parse_if_match

log = logging.getLogger(__name__)


def add_settings_routes(app: FastAPI, settings: SettingsService) -> None:
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
            return JSONResponse({"errors": [error_item(str(e))]}, status_code=422)
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
        expected = parse_if_match(request.headers.get("if-match"))
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON") from None
        if not isinstance(body, dict) or "value" not in body:
            raise HTTPException(400, 'body must be {"value": ...}')
        try:
            revision, _ = settings.update(section, body["value"], expected, source="ui")
        except ConfigError as e:
            return JSONResponse({"errors": [error_item(str(e))]}, status_code=422)
        except RevisionConflict as e:
            current = settings.public_sections().get(section, {})
            return JSONResponse(
                {"detail": str(e), "current_revision": e.current_revision,
                 "value": current.get("value")}, status_code=409)
        log.info("settings: %s saved (revision %d)", section, revision)
        value = settings.public_sections()[section]["value"]
        return {"revision": revision, "value": value, "applied": True}
