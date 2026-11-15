# Card: Document practice mode

**Status:** done 2026-11-15 (awaiting review)
**Target files:** DECISIONS.md, PLAN.md, docs/game-day.md (the only files to edit; fold the README and ARCHITECTURE lines into card 72 if it has not run yet)
**Goal:** The practice-mode decisions and the game-day steps are written down.

## Contract
- DECISIONS.md: no extra ESPN calls; plays are `play` events with status `practice` that never fire; practice resets on restart; play lag is a starting estimate only and never changes per-kind score delays; retention 7 days; what is unverified (see below)
- `docs/game-day.md`: a short "Before kickoff" step: start practice at kickoff, mark about five plays, use the suggestion, then mark the first score to fine-tune
- State plainly that the play detection was built against a hand-made board, not a recording, until card 84 is done

## Done when
- [ ] The three files say the above and nothing else changed
- [ ] `uv run pytest` and `uv run ruff check` still pass
