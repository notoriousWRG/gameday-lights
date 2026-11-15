# Card: Split the page into static files

**Status:** done 2026-11-08 (awaiting review). Note: three scripts (`app.js`, `screens.js`, `nav.js`) plus `status.css`; the server reads them once at startup and serves them from memory at `/static/<name>`.
**Target files:** app/web/status.html, app/web/static/status.css, app/web/static/app.js, app/web/static/screens.js, app/web/status.py (the only files to edit)
**Goal:** The 1,300-line single page becomes a thin shell plus CSS and scripts, still with no build step.

## Contract
- `status.html` keeps the markup; CSS and JS move to `/static/`; the page and its assets are read once at startup so a page never meets a different API version
- Behavior and URLs unchanged; checked in a browser on every screen

## Constraints
- Do after card 69. Tests that read the page text read the new files. Follow CLAUDE.md.

## Done when
- [x] `uv run pytest` and `uv run ruff check` pass
- [x] Only the target files changed (plus the notes above)

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
