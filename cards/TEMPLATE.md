# Card: <short imperative title>

**Target files:** path/to/module.py, tests/test_module.py (the only files to edit)
**Goal:** one or two sentences describing the behavior after this change.

## Context to read (read-only)
- path/to/related.ext: why it matters (a signature, a schema, a caller)
- ARCHITECTURE.md: the section on this module

## Contract
- Function signatures, types or schema fields that must hold
- Names to use exactly

## Constraints
- Conventions to follow (see CLAUDE.md)
- Do not touch: other files, public APIs

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] Example: input X gives output Y
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
