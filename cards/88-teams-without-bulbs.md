# Card: A followed team may have no bulbs

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/config.py, app/dispatch/dispatcher.py, app/settings_service.py, app/web/static/screens.js (Teams screen), app/web/static/app.js (status label), tests/test_config.py, tests/test_dispatcher.py, tests/test_settings_service.py, tests/test_web_status.py (the only files to edit)
**Goal:** A team can be followed with an empty bulb list: swap or clear its lights, or turn its notifications off, and still save. Scores are still detected and recorded; nothing lights.

## Context to read (read-only)
- app/config.py: `parse_config` (`teams[i].bulbs: list of bulb names required` is what blocks the save)
- app/dispatch/dispatcher.py: the planner loop over `team.bulbs` (an empty list already yields no plans)
- app/web/static/screens.js: `follow` (refuses with "Add a bulb first") and the team row's Test button (disabled with no bulbs)
- DECISIONS.md: "Score firing" and "Restart" rows (events are stored whether or not they fire)

## Contract
- `teams[i].bulbs` may be `[]`; the key may be missing (means `[]`). Every name listed must still exist ("unknown bulb" stays an error), and no duplicate names
- An event for a team with no bulbs is stored as usual and marked as fired with nothing to play (no lights, no error); the status page recent-events row says "no lights" for it
- Teams screen: **Follow** works with zero bulbs configured (the new team starts with none); a team row with no bulbs shows "No lights: scores are recorded but nothing flashes", and its Test button stays disabled with that reason
- Removing the last bulb from a team and saving works; so does saving with no bulbs in the system at all
- The bulbs section may be empty; the Bulbs screen shows the existing "No bulbs configured" text

- The event's status is `no_lights` (status page shows "no lights"), not `failed`
- Settings writes clean up after themselves (found 2026-11-15: a removed bulb left its per-team chase override behind and every save then failed with "unknown bulb", so a dead bulb could never be removed): saving `teams` drops each team's `fixture_effects` for bulbs not on that team; saving `bulbs` drops `effects.fixtures` for bulbs no longer present (and writes the effects section)

## Constraints
- Do not add a per-team "notifications off" flag: an empty bulb list is the off switch, so there is one way to say it
- Do not touch the flash cap, the bulb adapters, or the store schema

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] Example: a config with a team `bulbs = []` loads; a score for that team is recorded and nothing is sent to any bulb
- [ ] Example: the Teams screen saves a team after its last bulb is unticked
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
