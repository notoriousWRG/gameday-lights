# Card: Diagnostics screen with Copy bundle

**Target files:** app/web/static/ (new diagnostics screen file plus nav entry), app/web/status.html, tests/test_web_status.py
**Goal:** A Diagnostics tab shows the C90 data as plain rows (green/red for health) with a **Copy for text message** button that copies `bundle`.

## Context to read (read-only)
- cards/90-version-diagnostics-api.md; existing screens in app/web/static/

## Constraints
- No build step, vanilla JS like the other screens. Works on a phone.
- Clipboard fallback: if `navigator.clipboard` is missing (plain http on LAN), select the text for manual copy.

## Done when
- [ ] pytest and ruff pass
- [ ] The tab renders in dry-run and Copy works (check in a browser)
