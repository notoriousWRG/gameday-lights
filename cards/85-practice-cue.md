# Card: Optional light cue on each play (later, only if wanted)

**Status:** idea, not drafted for building; depends on 80 to 82 being used in a real game
**Target files:** decide after use
**Goal:** Instead of pressing a button when you see a play, a small cue lights the lamp at each play after the current delay, and you tap **earlier** or **later** to nudge the delay by one second.

## Notes
- Faster to tune than button presses, but flashes the lamp on every play for the whole practice window, so it should be off unless asked for and use a gentle, single, slow change well under the 2 changes/sec cap
- It goes through the dispatcher and the bulb adapter like any effect (snapshot and restore), never directly
- Build only if the button version proves too slow or too inexact in a real game
