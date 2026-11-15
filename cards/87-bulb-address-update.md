# Card: Discovery shows a moved bulb and updates its address

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/web/routes_bulbs.py, app/web/static/screens.js (the Bulbs screen only), tests/test_web_settings.py, tests/test_web_status.py (the only files to edit)
**Goal:** The Bulbs screen no longer says "already there" for a bulb whose address changed; it says the address moved and offers one button to fix it.

## Context to read (read-only)
- app/web/routes_bulbs.py: `discover` (matches by MAC or, without a MAC, by IP)
- app/settings_service.py: how the `bulbs` section is saved with its revision (`If-Match`)
- DECISIONS.md: "Edit access" and "Live apply" (a bulb change swaps the adapter at runtime)

## Contract
- Each discovery row gains `stored_ip` (the saved IP, or null) and `moved` (true when matched and `stored_ip != ip`)
- Bulbs screen: a moved row reads "<name> is now at <ip> (was <stored_ip>)" with an **Update address** button; an unmoved known row keeps "already added"
- **Update address** saves the new IP for that bulb through the normal `bulbs` settings write (revision, `X-Gameday`), keeping name, kind, segments, key and team links; the adapter is rebuilt by live apply
- A stale revision (409) or a validation error shows the same message as any other Bulbs save

## Constraints
- Update only the `ip` field; never change `mac`, name or the signing key
- The screen suggests a DHCP reservation in one line of help text; no router calls
- Do not touch: adapters, other screens

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] Example: stored .27, found .108, same device id: the row shows the move and **Update address** saves .108
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
