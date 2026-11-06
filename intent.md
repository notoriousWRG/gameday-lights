# Game Lights — Intent Document

Oct 29, 2026 · @WR

## Vision in brief

A small, always-on home server that knows when my teams are playing, watches those games live, and turns big moments into light in the room. When the Packers score, the living room flashes green and gold; when the Penguins score, black and gold. A tiny web app lets anyone in the house pick teams and choose what each event looks like. It should feel like part of the house, not another screen to check.

Three outcomes define success:

1. **It just knows.** Following a team is a one-time setup. The server finds scheduled games, wakes up for them, and goes quiet afterward with no manual start.
2. **The room reacts with the TV, not before it.** A score lights the room at about the moment we see it on screen. It never spoils a play we haven't watched yet.
3. **Easy to extend.** Scores ship first. Penalties, turnovers, period ends and final results can be added later as new event types without reworking anything.

## Why build it

- **Shared moments.** Game time is family time. The lights are for the whole room, the kids included, and should make watching together more fun. That is the measure, not technical polish.
- **No phone required.** The signal lives in the room, which fits the move away from smartphones. "Notifications" here means lighting events. Game-event alerts on other channels are optional and come later; the one exception is health alerts to me when an install breaks.
- **A gift.** A few close family and friends will get a bulb and run it on a home server they already have. Game time is shared time for them too.
- **A clean hack project.** A small scope, a public data source, and a hardware payoff make it a good first real test of the task-card workflow from the Local AI Workbench (see Handoff).

## Scope

**In v1**

- Follow teams in the NFL and NHL (the Packers and Penguins to start), modeled so other ESPN leagues fit later
- Find each team's upcoming games and schedule a watch window
- Poll live games and detect score changes for followed teams
- Map each event to a light effect (team colors, flash pattern, duration) on one or more bulbs
- A minimal LAN web app: follow or unfollow teams, assign bulbs, set the effect and delay for each event, and a "test effect" button
- Streaming-aware delay: delay profiles, a live ±5 second nudge, a calibration helper and a Hold toggle (see The delay problem)
- Quiet hours and a brightness cap
- Portable install for Linux, Mac and Windows, with health alerts to me (see Gifting and distribution)

**Later (designed for, not built)**

- More event types: penalties, turnovers, power plays, end of period, win or loss at the final whistle
- A pregame cue, such as a slow pulse 5 minutes before kickoff
- Game-event alerts on other channels (desktop, email, chat), only if they turn out to be wanted. Health alerts to me are separate and are in Phase 2.5.
- Other leagues, college teams

**Out of scope**

- Mobile apps, user accounts, or anything publicly exposed to the internet (private-network remote help, such as Tailscale, is fine)
- A hosted service for other people: gifts run on the recipient's own hardware (see Gifting and distribution)
- Video sync or reading the TV signal
- Betting or odds data

## The data source: ESPN's unofficial API

The [pseudo-r/Public-ESPN-API](https://github.com/pseudo-r/Public-ESPN-API) repo documents ESPN's public endpoints. Most need no authentication. **The API is unofficial and may change without notice.** No rate limits are published, but heavy use can get blocked, so caching and backoff are required.

| Need | Endpoint (site API unless noted) | Notes |
| --- | --- | --- |
| Team list and IDs | `site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams` | Used to set up follows; cache it for a day or longer |
| Team schedule | `.../sports/{sport}/{league}/teams/{id}/schedule` | Source for watch windows |
| Scoreboard (live and scheduled) | `.../sports/{sport}/{league}/scoreboard?dates=YYYYMMDD` | Cheapest live check: one call covers every game that day |
| Game summary | `site.api.espn.com/apis/site/v3/sports/{sport}/{league}/summary?event={id}` | Richer schema; useful for later event types |
| Plays (play-by-play) | `sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/plays` | Needed for penalties and other non-score events |
| CDN live alternative | `cdn.espn.com/core/{sport}/scoreboard?xhr=1` and `.../playbyplay?xhr=1&gameId={id}` | Fallback if the site API is slow or blocked |

League paths: NFL is `football/nfl` and NHL is `hockey/nhl`. NHL standings use a separate path (`/apis/v2/sports/hockey/nhl/standings`), which matters only if standings ever enter scope.

**Detection strategy**

- **v1 (scores):** poll the scoreboard and diff each followed team's score against the last stored value. An increase is a score event; the size of the jump hints at the type (6/3/2/1 in the NFL, 1 in the NHL). Simple, one call per poll, and robust to schema details.
- **Later (non-score events):** poll the plays feed for live games only and dedupe on the play ID. Penalties, turnovers and similar events come from play types here.
- **Corrections:** scores sometimes go *down* (a reversed touchdown, a disallowed goal). Store the new value and fire nothing in v1; a "reversal" effect could come later.

## How the server works

One process, three loops, and SQLite for state.

1. **Schedule sync (every few hours).** For each followed team, fetch the schedule and upsert upcoming games with start times.
2. **Game watcher.** Starting about 10 minutes before a game, poll its scoreboard every 10–15 seconds while it is live. Back off to 60 seconds during long breaks such as halftime and intermissions. Stop when the status reads final.
3. **Effect dispatcher.** Each detected event goes into a queue, waits for its configured delay, checks quiet hours, then plays the effect on the assigned bulbs and restores their previous state.

Design rules:

- **The bulb is an adapter.** One interface (`set_color`, `flash(pattern)`, `snapshot`/`restore`) with one implementation per brand. The rest of the app never knows the brand.
- **ESPN is an adapter too.** Every ESPN call goes through one client with caching, a timeout, and backoff, so a schema change breaks in one file.
- **Events are data.** An event is stored as `{game, team, type, detail, detected_at}`. New event types are new detectors that emit the same shape.
- **Idempotent.** Restarting mid-game never replays old events, because every event has a dedupe key.
- **Config is data.** Team colors, polling intervals, delays and quiet hours live in the database or a config file, not in code.

## The delay problem (the most important design detail)

ESPN data and the TV picture are not in sync, and the gap depends on how we watch. Streaming services often run tens of seconds behind live, sometimes more. If the lights fire on the ESPN update, they can spoil the play before we see it. If ESPN lags our broadcast instead, the lights arrive late and feel disconnected.

- Make the **broadcast delay a per-household setting**, with a slider in the app and a "calibrate" helper: press a button when the score shows on TV, and the app records the gap against the event it detected.
- Default to a conservative delay. A late flash is a small miss; a spoiler ruins the moment.
- Log the detection time and the effect time for every event so the delay can be tuned from real numbers.

**Streaming is the primary viewing mode, so the delay is core, not a nicety.** Streams typically trail the live feed, and the lag can differ by service, by device and even by game (the same team can be on a different service week to week). That shapes the design:

- **Delay profiles.** A household default plus named profiles (for example "Peacock" or "YouTube TV") that can be switched per game. Profile values come from measurement, not guesses.
- **Live nudge.** ±5 second buttons in the app that apply to the next event, so anyone in the room can tune the delay mid-game in a few taps.
- **Calibration is a v1 feature.** The "I just saw it on screen" button is built in Phase 2, and Phase 0 measures real lag on the services we use.
- **Pause and rewind.** Pausing or rewinding a stream puts the lights ahead of the picture. A **Hold** toggle (the same switch as the kill switch) suspends effects, and its behavior on resume (skip or replay missed events) is a setting.

I have not measured ESPN's update latency; Phase 0 does.

## Smart bulbs: LIFX first, WiZ second, confirmed in Phase 0

Selection criteria, in order: **local LAN control** (no cloud round trip, still works when a vendor's cloud is down), fast enough response for a flash pattern, good saturated colors (green and gold have to read clearly), and a documented or well-known protocol.

| Option | Hub | Local control | Price (approx.) | Notes |
| --- | --- | --- | --- | --- |
| Philips Hue | Hue Bridge (~$50) | Local REST API on the Bridge, LAN-only. Hue's docs suggest ~10 commands/sec per light and 1/sec per group. Entertainment API streams at up to 20 Hz but needs an Entertainment Area set up in the Hue app. | ~$45/bulb | Excellent color; Zigbee response ~150–200 ms. Rate limits are fine for flashes; the Entertainment API is overkill for score events. Only worth the bridge cost for a whole-room setup. |
| LIFX | None (Wi-Fi) | Official, documented LAN protocol: UDP port 56700, broadcast discovery (all devices) or mDNS (firmware 4.110+), optional acknowledgements | ~$40/bulb | Best docs of the group and rated most vibrant color; no hub. Per-device message rate is not published; measure it in Phase 0. |
| WiZ | None (Wi-Fi) | Local UDP control via community library [pywizlight](https://pypi.org/project/pywizlight) (broadcast discovery; on/off, brightness, RGB, scenes; v0.6.6, Aug 2026). Unofficial, reverse-engineered protocol. | ~$12/bulb | Cheapest; Wi-Fi congestion risk past ~15 bulbs. Port (38899) and a possible "allow local communication" toggle in the WiZ app are from memory; confirm when the bulb arrives. |
| Govee | None (Wi-Fi) | LAN API over UDP (multicast 239.255.255.250; scan on 4001, commands on 4003); must be turned on per device in the Govee app; supported models only | Varies | Devices don't push state (poll only) and the built-in color fade can interfere with fast changes. Skip unless Govee gear is already owned. |
| Home Assistant | Whatever you own | One API in front of all of the above | — | Avoids writing adapters; adds a whole platform to run |

Price and color notes come from [Smart Home Explorer's 2026 comparison](https://www.smarthomeexplorer.com/guides/philips-hue-vs-lifx-vs-wiz-2026). Local-control details come from the [LIFX LAN protocol docs](https://lan.developer.lifx.com/docs/communicating-with-device), [pywizlight](https://pypi.org/project/pywizlight), the [Hue developer docs](https://developers.meethue.com/?p=497), the [Home Assistant Govee LAN thread](https://community.home-assistant.io/t/govee-news-theres-a-local-api/460757) and the [openHAB Govee LAN binding docs](https://www.openhab.org/addons/bindings/govee/). Every candidate supports local control (Hue via its bridge), so no cloud API is needed. Latency on our own Wi-Fi is still unmeasured; Phase 0 does that.

**Decision:** buy one **LIFX** bulb first. It has the only official, documented local protocol and the most saturated color, which matters because green and gold must read clearly. Buy one **WiZ** bulb as a cheap second test (~$12) to compare color and latency; if it is good enough, it is much cheaper to put in several rooms. Decide on Hue only if a whole-room setup becomes the goal. Because the bulb is an adapter, both can coexist and the choice stays cheap to change.

## The app

- A single-page LAN web UI served by the same process. No login (LAN only).
- Screens: **Teams** (search, follow, colors pre-filled from ESPN team data), **Bulbs** (discover or add by IP, name, group freely; any event can target any bulb or group), **Effects** (event type to pattern, color and duration), **Settings** (delay profiles and nudge, calibration, Hold, quiet hours, brightness cap).
- A **Test** button on every effect, so the kids can trigger a Packers touchdown in the living room any time.
- An **Upcoming games** list showing what the server is going to watch.

## Household guardrails

- **Quiet hours.** Late games and a sleeping one-year-old don't mix. Outside set hours, effects are dimmed or skipped per room.
- **Brightness and flash limits.** Cap brightness and flash rate. Keep strobe-style patterns slow; rapid full-brightness flashing is uncomfortable for some people and is a known trigger for photosensitivity.
- **Kill switch.** One toggle in the app pauses everything (a "we're not watching tonight" mode).
- **Restore state.** Lights always return to how they were before the effect.
- **Health alerts to me.** An install that breaks quietly is found out on game day. Two parts:
  1. **Heartbeat from outside.** Each install pings a monitoring URL on a schedule; the monitor emails me when pings stop. This catches a crashed process, a powered-off server or lost internet, none of which can report themselves. It needs no mail credentials on the recipient's server. Pick a service (a healthchecks.io-style tool) and confirm its current free-tier terms first.
  2. **Failure message from inside.** When the app is alive but unhealthy (ESPN failing for N minutes, a bulb unreachable), it sends a short message through a pluggable notifier. v1: email (SMTP) and a generic webhook. SMS is a later notifier, since carrier email-to-text gateways are unreliable and real SMS services need signup and cost.
  
  The alert address is set by me in the config. Recipients never see or configure it, and the in-app email is optional because SMTP setup is friction on a gift.

## Hosting

The server needs to be on during game times and on the same LAN as the bulbs.

- **Mac mini:** already the always-on media server; the best fit if the PC sleeps or reboots into games. Run it natively under launchd (see the Docker note below).
- **Pop!\_OS PC:** fine for development; less reliable as an always-on host.
- **Raspberry Pi or similar:** the cleanest separation if one is on hand.

Develop on the PC and deploy wherever is always on. Run it as a single service (systemd, launchd or a Windows service) with SQLite on local disk.

**Decision for my own setup:** the Mac mini is the long-term home; the Pop!\_OS PC is the dev box. Both will see real use early on, so they must not step on each other:

- **Separate state.** Each instance has its own SQLite file and config; nothing is shared or synced.
- **One instance drives a given bulb at a time.** If both watch the same game and both fire, the bulb gets double effects. Each instance has an explicit `dispatch_enabled` flag; the dev instance defaults to **dry-run** (log the effect, don't send it) unless it is given its own test bulb.
- **Replay mode for dev.** Develop against recorded ESPN fixtures so work on the PC doesn't depend on a live game or on the Mac mini being idle.
- **Same code, different config.** Only the config file and the install wrapper differ between the two machines, which is also the first test of the "portable across OSes" rule.

## Gifting and distribution

The system should work for people other than me. A few close family and friends get a bulb and run the same app on a home server they already have. This is a hack project: if a gift breaks they text me and we fix it, and if it eventually dies, it had a good run. That is an acceptable support promise, so there is no hosted service, no accounts and no uptime obligation.

- **One codebase, no gift-only features.** Teams, leagues, event types and bulb brands stay configuration, so nothing in the code assumes the Packers, the Penguins or my house.
- **Ship the bulb, not hardware.** I standardize gift bulbs on one brand (LIFX or WiZ, decided in Phase 0). The other adapters remain for my own use.
- **Two supported install paths, deliberately few:**
  1. **Native install** (venv plus a systemd unit, a launchd unit or a Windows service/scheduled task) for Linux, Mac and Windows. This is the primary path.
  2. **Docker Compose** for Linux hosts and NAS boxes (Unraid, Synology, TrueNAS), added only when a recipient needs it.
- **Docker networking caveat.** Bulb discovery uses UDP broadcast (LIFX, WiZ), which does not cross Docker's default bridge network. The Compose file uses `network_mode: host`, which works on Linux but, as far as I know, not on Docker Desktop for Mac or Windows. So bulbs must also be addable by static IP, skipping discovery, and the native path is the answer for Mac and Windows hosts.
- **Setup is a short document.** `docs/SETUP.md`: install, open the local web page, follow a team, add the bulb, press Test. The bulb itself still has to be joined to their Wi-Fi with the vendor's app first; this step cannot be removed.
- **Supportability.** A Diagnostics page shows version, last ESPN poll, last event, bulb reachability and a copy-to-clipboard bundle recipients can paste into a text to me. Optional Tailscale gives me private remote access when someone asks.
- **Updates.** Tagged releases. Docker users pull a new image; native users run `./update.sh`. Updating is manual by default, because silent auto-updates on someone else's server is a trust question I'd rather ask first.

**Rollout order.** Prove it for me first, then expand:

1. **Pop!\_OS (this machine)**: development and the first full run. Phase 0 and Phase 1 happen here.
2. **Mac, native install**: a launchd unit and an install script, tested on the Mac mini.
3. **Windows**: most likely what the gift recipients run, so it is the install path that matters most for gifts even though it is tested third. The native Windows install (Python plus a service wrapper or Task Scheduler entry) is the primary Windows path. Docker Desktop on Windows has the same host-networking limitation as on Mac, so Compose is not the answer there.
4. **Linux and NAS boxes via Compose**: only if a recipient needs it.

Because Windows is the main gift target, keep the code portable from day one: `pathlib` for paths, no systemd or fork-only assumptions in app code, services and scheduling wrapped in thin per-OS install scripts, and a note in `docs/SETUP.md` about the Windows firewall prompt that appears for local UDP traffic.

**Tradeoff to name:** every friend's setup is one more environment I may end up debugging. Keeping the supported paths narrow, and shipping Diagnostics in Phase 2.5, is what keeps the gift from becoming a chore for either of us.

## Suggested stack

Keep it boring and small enough for single-file task cards.

- **Python 3.12 + FastAPI** (API and static UI), **httpx** (ESPN client), **APScheduler** or a plain asyncio loop for scheduling, **SQLite** for state
- **Native install scripts per OS** (Linux, Mac, Windows) for distribution, with Docker Compose as an optional extra (see Gifting and distribution)
- A plain HTML + vanilla JS front end, or HTMX. No build step.
- **pytest** with recorded ESPN JSON fixtures, so tests never hit the live API

Recorded fixtures matter: they let detectors be tested against a real past game (including a reversed score) without waiting for Sunday.

## Risks and open questions

| Risk | Likelihood | Guardrail |
| --- | --- | --- |
| ESPN changes or blocks endpoints | Medium | One client module, caching, backoff, CDN fallback, fixture tests that show what changed |
| Lights spoil plays on a delayed stream | High without tuning | Per-service delay profiles, live nudge, a calibration helper, a Hold toggle, a conservative default |
| Bulb brand lacks dependable local control | Medium | Adapter interface; prove one bulb before buying more |
| Discovery fails on a friend's network (Docker bridge, VLANs, mesh routers) | Medium | Static-IP bulb entry, host networking in Compose, native install path, Diagnostics page |
| Supporting many different home servers | Medium | Two supported install paths only; copy-paste diagnostics bundle; the "good run" support promise |
| Polling too aggressively | Low | Poll only during live windows; one scoreboard call covers all followed games in a league |
| The project becomes the hobby | Medium | Phases with exit gates; v1 is scores only |

**Open questions**

- Brand: LIFX first, WiZ as the second test; Phase 0 confirms. Rooms are deliberately not decided ahead of time: bulbs are named and grouped in the app, and any event can target any bulb or group.
- Which streaming services do we watch on, and what is the measured lag for each? (Streaming is the main mode; Phase 0 measures it.)
- ~~Which box hosts it long-term for me?~~ Decided: Mac mini long-term, Pop!\_OS PC for dev, with the dry-run rule above. (For gifts: the recipient's existing home server.)
- Which hosts do the gift recipients run? Most appear to be Windows, so a Windows install path is the one that matters most for gifts (see rollout order).
- ~~Is any non-light notification wanted?~~ Decided: lights only for game events. The one exception is **health alerts to me** when an install breaks (see Health alerts under Household guardrails).
- A final-win celebration effect is wanted. Its design waits until Phase 0 shows what the bulbs can actually do (color range, flash rate, any multi-bulb choreography). Not committed to v1 yet.

## Phased roadmap

**Phase 0: Prove the pieces (one to two weekends; needs at least one live game, on Pop!\_OS)**
Pull a live NFL or NHL scoreboard and log score changes during a real game, with timestamps. Flash one bulb from a script over local control, and test rapid command bursts for dropped packets and the per-device message rate. Measure ESPN lag against our TV. *Gate:* a score is detected within a known, stable delay, and the bulb responds locally in under a second.

**Phase 1: Server MVP**
Schedule sync, game watcher, score detector, dispatcher with delay, SQLite, config file for teams and bulbs. No UI. *Gate:* a full Packers or Penguins game runs unattended, with correct effects and no replays after a restart.

**Phase 2: The app**
Teams, bulbs, effects, settings, test buttons, upcoming games, quiet hours, a kill switch and Hold, plus the streaming-delay features: delay profiles, live nudge and the calibration helper. *Gate:* someone other than me sets up a team and an effect without help.

**Phase 2.5: Package for others**
Diagnostics page, health alerts (heartbeat plus an email notifier), native install and update scripts (Linux, then Mac, then Windows), optional Compose file, `docs/SETUP.md`. *Gate:* a friend on their own machine (Windows first) goes from zero to a working Test flash using only `docs/SETUP.md`.

**Phase 3: More events**
Plays-feed detector; penalties first, then turnovers and a final win or loss. *Gate:* new event types added without touching the bulb or dispatcher code.

## Handoff to Claude Code

Put this file in a new repo as `intent.md` and add a `CLAUDE.md` with the rules below. Build Phase 0 first. This project is a good first run of the task-card workflow: most modules are single files with clear contracts (the ESPN client, the score detector, each bulb adapter, the dispatcher).

**Suggested repo shape:** `intent.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `PLAN.md`, `cards/`, `app/espn/` (client and detectors), `app/bulbs/` (one adapter per brand), `app/dispatch/`, `app/web/`, `tests/fixtures/` (recorded ESPN JSON), `scripts/` (Phase 0 probes), `deploy/` (Compose file, systemd and launchd units, install and update scripts), `docs/SETUP.md`.

**Rules for `CLAUDE.md`**

- Every ESPN call goes through `app/espn/client.py`; never call ESPN from anywhere else.
- Tests never hit the network; use recorded fixtures.
- Bulbs are only touched through the adapter interface; always snapshot and restore state.
- Polling intervals, delays, colors and quiet hours are config values, never hard-coded.
- Never poll faster than every 10 seconds; poll only during live windows.
- Nothing binds outside the LAN, and there are no cloud bulb APIs in v1. Outbound calls are limited to ESPN, the heartbeat URL and the configured notifier.
- Bulbs must be addable by static IP as well as discovered; discovery can fail inside containers and across VLANs.
- Nothing assumes a specific team, league, brand, host OS or household; all of it is configuration.

**First prompts, in order**

1. *ESPN probe.* "Read intent.md. Write `scripts/probe_scoreboard.py`, which polls the NFL or NHL scoreboard every 15 seconds for a given team, logs each score change with a timestamp to CSV, and saves every raw response to `tests/fixtures/` for later replay."
2. *Bulb probe.* "Write `scripts/probe_bulb.py` for <brand>: discover the bulb on the LAN, snapshot its state, flash two colors three times, restore the state, and print the round-trip time per command."
3. *Detector.* "Write `app/espn/detect.py`, a pure function that takes the previous and current scoreboard JSON and the followed team IDs and returns a list of score events. Test it against the recorded fixtures, including a score that goes down."

**Acceptance checks for Phase 0**

- [ ] At least one live game logged with every score change and its timestamp
- [ ] ESPN-to-TV delay measured for how we actually watch
- [ ] One bulb flashed and restored over local control; latency and burst behavior recorded
- [ ] LIFX and WiZ test bulbs compared on color (green/gold) and latency; brand decided, or a third option chosen
- [ ] WiZ local-control details (port, app toggle) confirmed

## Sources

- [pseudo-r/Public-ESPN-API (GitHub)](https://github.com/pseudo-r/Public-ESPN-API)
- [Philips Hue vs LIFX vs WiZ 2026 (Smart Home Explorer)](https://www.smarthomeexplorer.com/guides/philips-hue-vs-lifx-vs-wiz-2026)
- [Govee LAN-API Binding (openHAB)](https://www.openhab.org/addons/bindings/govee/)
- [Govee local API discussion (Home Assistant community)](https://community.home-assistant.io/t/govee-news-theres-a-local-api/460757)
- [LIFX LAN Protocol: Communicating with a device](https://lan.developer.lifx.com/docs/communicating-with-device)
- [pywizlight (PyPI)](https://pypi.org/project/pywizlight)
- [Philips Hue developer docs](https://developers.meethue.com/?p=497)
