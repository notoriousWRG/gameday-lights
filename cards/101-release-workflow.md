# Card: Tagged release builds

**Target files:** .github/workflows/release.yml (new), CHANGELOG.md (new), docs/releasing.md (new), pyproject.toml (version only, when releasing)
**Goal:** Pushing a tag `vX.Y.Z` that matches `pyproject.toml` runs tests, builds the wheel and sdist with `uv build`, and publishes a GitHub Release with the wheel, `bootstrap.sh`, `bootstrap.ps1` and notes from CHANGELOG. `docs/releasing.md` is the five-step checklist (bump, changelog, tag, push, verify on the Mac mini first).

## Constraints
- Release assets keep stable names so the docs' one-liners can point at `releases/latest/download/...`.

## Done when
- [ ] Workflow lints; a dry tag in a fork or the user's first tag produces the assets
