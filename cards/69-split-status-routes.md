# Card: Split status.py by area

**Status:** done 2026-11-08 (awaiting review). Note: besides the four routes_* modules there are `common.py` (helpers, `BulbGuard`) and `data.py` (what the page shows). `BulbPings`, `create_app`, `PAGE` and `serve_status` stay in status.py because tests patch them there.
**Target files:** app/web/status.py, app/web/routes_settings.py, app/web/routes_teams.py, app/web/routes_bulbs.py, app/web/routes_effects.py (the only files to edit)
**Goal:** The 650-line web module becomes `create_app` plus one routes module per area.

## Contract
- `create_app` signature and every URL stay the same; each module exposes `add_<area>_routes(app, ...)`
- Shared guards (`X-Gameday`, `If-Match`, the pulse `ready`/`play`) move to one small helper module

## Constraints
- Tests are not edited; they must pass as they are. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
