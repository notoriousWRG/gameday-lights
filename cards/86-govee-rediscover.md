# Card: Govee finds its strip again when the IP changes

**Status:** done 2026-11-15 (awaiting review)
**Target files:** app/bulbs/govee.py, tests/test_bulbs_govee.py (the only files to edit)
**Goal:** When the strip stops answering at its stored IP, the adapter scans for its device id and carries on at the new IP, as the WiZ adapter does.

## Context to read (read-only)
- app/bulbs/wiz.py: `_rediscover` and `_call` (search by MAC, update `self.ip`, retry once)
- app/bulbs/govee.py: `discover_govee`, `GoveeBulb._send`, `_status`, `ping`, `restore`
- DECISIONS.md: "Bulb IP" row (store IP and MAC; re-discover by MAC if the IP stops answering)

## Contract
- Seen 2026-11-15: the H616D moved from 192.168.0.27 to 192.168.0.108 (DHCP). The stored IP went stale and every pulse check failed with `BulbUnreachable`
- `GoveeBulb._rediscover() -> bool`: false at once if `self.mac` (the device id) is unset; otherwise `discover_govee(transport=self._transport)`, find the entry whose `mac` equals `self.mac`, set `self.ip`, clear the cached on/brightness state so every command is re-sent, log a warning with the old and new IP; false if not found
- Used when `_status` finds no answer on all attempts (the query path), and when `_send` raises `OSError`; retry the command once after a successful rediscovery. UDP sends have no acknowledgement, so a `_send` that raises is the only send-side signal; the query path is what catches a silent stale IP, so `snapshot()` and `ping()` must go through it
- `ping()` stays a single direct check with no rediscovery (like WiZ), so the status page tells the truth about the stored IP
- At most one scan per call, never more often than once every 30 s per bulb, so an off strip does not trigger a scan per command

## Constraints
- Scans use the existing transport; no new network paths. Tests use a fake transport (CLAUDE.md: never the network)
- Do not touch: the discovery route or settings; persisting the new IP is card 87

## Done when
- [ ] `uv run pytest` passes
- [ ] `uv run ruff check` passes
- [ ] Example: a strip stored at .27 that answers only at .108 gets its snapshot read after one scan, and later commands go to .108
- [ ] A strip that is off or gone logs one warning, raises `BulbUnreachable`, and does not scan again within 30 s
- [ ] Only the target files changed

## If stuck
Stop and report what you tried and the exact error. Do not repeat a failed action more than once.
