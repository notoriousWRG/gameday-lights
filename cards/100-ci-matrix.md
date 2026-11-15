# Card: CI on Linux, macOS and Windows

**Target files:** .github/workflows/ci.yml (new)
**Goal:** On push and PR run `uv sync`, `uv run ruff check` and `uv run pytest` on ubuntu, macos and windows runners (Python 3.12). Windows failures are the early warning for path and newline bugs.

## Done when
- [ ] Workflow lints (actionlint if available); first run (user pushes) is green or its failures are listed as cards
