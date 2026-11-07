# Card: Effects screen with Test button

**Target files:** app/web/status.html, tests/test_web_status.py
**Goal:** An `Effects` screen (`#/effects`) to edit the score effect (the `effects` section) and try it on a bulb.
**Contract:**
- Fields: pulses (integer, min 1), duration in seconds (min 0.1), brightness (1 to 255, shown as a percent), color and alternate color, each with a "Use team colors" reset (null = each team's own colors; team colors in Teams take precedence over these, say so in a hint)
- Live preview of the pattern as a row of swatches alternating the two colors (team colors unknown here, so show the effect colors or a neutral placeholder when blank)
- Shows the flash rate (`pulses*2 / duration_s` changes per second) and warns as it nears the 2/sec cap; the server's 422 is still the authority and its message shows under the field
- Test button: pick a bulb (select, defaults to the first), `POST /api/bulbs/{name}/pulse` exactly as the Status page does (reuse its handler and state, so busy/cooldown/dry-run notes behave the same); disabled while the draft is unsaved, with the note "Save to test your changes" (the pulse plays the saved pattern)
- Built on `sectionEditor` from card 34; no server changes
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser (edit, 422 for too-fast pulses, Save, Test in dry-run); only the target files changed.
