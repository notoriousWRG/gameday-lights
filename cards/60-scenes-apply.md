# Card: Apply and save scenes

**Status:** drafted 2026-11-08
**Target files:** app/web/status.py, app/web/status.html, app/settings_service.py, tests/test_web_status.py, tests/test_settings_service.py (the only files to edit)
**Goal:** Save the current lights as a scene and apply a scene to all its bulbs with one tap; export carries scenes.

## Contract
- `POST /api/scenes/{name}/apply` sets every bulb in the scene through `Dispatcher.set_state`, reporting per-bulb results
- Lights screen: scene buttons, "Save current as scene" (reads each bulb's current state), delete
- TOML export writes `[[scenes]]`; renaming a bulb renames it inside scenes
- Needs cards 55-59

## Constraints
- Writes go through the settings API with If-Match, like other sections. Follow CLAUDE.md.

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
