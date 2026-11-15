# Card: Record plays while practice mode is on

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/watcher.py, app/store.py, tests/test_watcher.py, tests/test_store.py (the only files to edit)
**Goal:** While practice mode is on, each new play in a watched live game is stored as a `play` event that never fires any light. Off, the watcher behaves exactly as before.

## Context to read (read-only)
- app/watcher.py `poll_once`, `_capture_live`, `_record`: where a board is seen and a score event is stored
- app/store.py `Event`, `insert_event`, `recent_events`, `pending_events`: a play must not appear as pending and must not push scores out of the recent list
- Card 79: `situation.last_play`, `clock`, `period`

## Contract
- `Watcher.start_practice(minutes: float) -> datetime` returns the end time; `stop_practice()`; `practice_until: datetime | None` (in memory, UTC; a restart turns it off, which is the safe default). `Watcher.practice_active(now)` is true until `practice_until` and false once every followed game has ended
- A play is new when a live game's `last_play.id` changes (or, if ESPN sends no id, when `situation.text` plus `period` and `clock` change). The first board seen after practice starts only sets the baseline; it records nothing
- Event: `type="play"`, `status="practice"`, `dedupe_key=f"play:{game_id}:{play id}"` (a timestamp when ESPN sends no id, so a restart cannot collide), `detail={"label": "Play", "text": <situation text or last-play text>, "period", "clock", "abbr": <possession>}`, `due_at=detected_at` (never scheduled; the dispatcher only reads `status='pending'`)
- `Store.recent_events` leaves out `type='play'` (the status page's list keeps showing scores); a new `Store.recent_plays(limit)` lists them; `seen_events` still returns played events once marked, so existing lag math works
- Plays older than 7 days are deleted at startup (`Store.prune_plays(before)`), so the table does not grow all season

## Constraints
- No change to polling: the same board, the same interval (never under 10 s). Practice only reads what the poll already fetched
- No effect, no dispatcher call, no bulb touched for a play
- Times in UTC; practice length is a config value (`web.practice_minutes`, default 20, 1 to 120) added in card 81, not hard-coded here: this card takes it as an argument

## Done when
- [ ] `uv run pytest` and `uv run ruff check` pass
- [ ] Practice off: a board with changing `last_play` stores nothing
- [ ] Practice on: three boards with three plays store three `play` events; a repeated board stores none; the first board only baselines
- [ ] A score during practice still creates and fires its normal `score` event
- [ ] `recent_events` excludes plays; `recent_plays` returns them newest first
- [ ] Only the target files changed
