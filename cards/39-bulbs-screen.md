# Card: Bulbs screen

**Target files:** app/web/status.html, tests/test_web_status.py
**Goal:** A `Bulbs` screen (`#/bulbs`) to add, edit and remove bulbs, check they answer, and test them.
**Contract:**
- Rows from the `bulbs` section: name (editable only on a not-yet-saved bulb, because teams refer to bulbs by name), IP, MAC (optional), port (default 38899), live reachability from `/api/status` (ms or "unreachable"), Ping-and-Test via the Status page's `pulse`, Remove
- Signing key is write-only: shown as "key set" / "no key" from `has_signing_key`; a password-type input sets a new one, a "Remove key" button clears it; an untouched key is omitted from the PUT so the server keeps it; the key is never put in text or logs
- Add by IP: name, IP, optional MAC and port, appended to the draft. Discover: button posts `/api/bulbs/discover` (spinner text, ~5 s), lists found bulbs with "Add" (disabled when `known`), prefilling IP and MAC and suggesting a free name
- Remove is disabled with a reason while a followed team uses that bulb (the server's 422 is the authority)
- Save through `sectionEditor` (`bulbs` section, 422 text under the row by index `bulbs[i].field`, 409 Load latest); a saved bulb is live at once; after Save show its reachability within one status refresh
- Teams screen's "Bulbs are set in config.toml for now" message is updated to point to this screen
**Done when:** `uv run pytest` and `uv run ruff check` pass; checked in a browser (add by IP, discovery with a stubbed result, 422 duplicate name, key stays set after an unrelated edit); only the target files changed.
