# Game day

## Before kickoff
1. Make sure the service is running the current code (a restart makes it skip any score that lands while it is down, so restart before kickoff, not during play).
2. Open **Calibrate**. When a followed game is about to begin, **Start practice mode** becomes available. It stays on for `[web] practice_minutes` (default 20) and turns itself off when it runs out or the service restarts.
3. Each play the app detects appears as a row. Press **I see it on TV** the moment the same play shows on your TV (the row's text matches the down-and-distance graphic). Lights do not flash for plays.
4. After about five marked plays, press **Use N s as starting delay**. It sets only the general delay.
5. On the first real score, mark it too: touchdowns and extra points can differ from plays by a few seconds. Then use the per-kind suggestions under **Scores**.

An unmarked score or play loses its button after `[web] mark_window_min` (default 5) minutes, and as soon as you mark a later one: a reading that late says little about the delay, and the server refuses it. Marked rows stay (so you can undo one) until they are 12 hours old. Readings keep counting toward the suggestions. Plays are deleted after 7 days.

## Caveat
Play detection was built and tested against a hand-made scoreboard, not a recording of a live game. Until it has been checked against one, treat "no plays appear" as something to report, not a fault in your setup.
