# Card: Docs site scaffold and GitHub Pages deploy

**Target files:** mkdocs.yml (new), docs/index.md (new), .github/workflows/docs.yml (new), pyproject.toml (docs dependency group only)
**Goal:** MkDocs (Material) builds `docs/` and deploys to GitHub Pages on push to master. Readable on a phone, light/dark, search on. `intent.md`, `PLAN.md`, `DECISIONS.md`, `cards/`, `docs/releasing.md` and `CHANGELOG.md` are not published.

## Constraints
- Keep `docs/game-day.md` where it is; nav lists the pages from C103.

## Done when
- [ ] `uv run --group docs mkdocs build --strict` passes
- [ ] User turns on Pages (Settings, Pages, source GitHub Actions)
