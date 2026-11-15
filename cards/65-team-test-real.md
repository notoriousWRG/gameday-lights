# Card: Teams screen Test plays the real effects

**Status:** done 2026-11-08 (awaiting review). Note: `make_team_pulse` was replaced by `make_team_test` and the create_app argument renamed `team_test`.
**Target files:** app/web/status.py, app/dispatch/dispatcher.py, app/web/status.html, tests/test_web_status.py, tests/test_dispatcher.py (the only files to edit)
**Goal:** The Teams Test button plays what the team really plays on each of its bulbs (chase on the strip, pulse on the lamp), with the colors as currently edited.

## Contract
- `POST /api/teams/test` builds one pattern per bulb through the same resolver as events, using the posted colors in place of the saved ones
- Response lists per-bulb results; one bulb failing does not stop the others
- `make_team_pulse` is no longer used by the web app (removal is card 68)

## Constraints
- Same guards, queue and restore as the pulse check. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
