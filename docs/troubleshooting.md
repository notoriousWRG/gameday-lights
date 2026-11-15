# When something is wrong

Open the **Diagnostics** tab first. It lists what the app sees: the version, whether ESPN and
your bulbs answer, and the last score. Problems also show up on the **Status** page under
**Finish setting up**.

You can check the whole setup from Terminal, too:

```bash
~/.local/bin/gameday-lights doctor
```

## The page won't open

Make sure you're on the computer where you installed it, and go to
<http://127.0.0.1:8787/>. If it still doesn't load, the app isn't running. On a Mac, start it
again and look at the end of the log:

```bash
launchctl kickstart -k gui/$(id -u)/com.gameday-lights
```

```bash
tail -n 30 ~/Library/Logs/gameday-lights.log
```

## It can't find my bulb

- The bulb is on, and on the **same Wi-Fi** as this computer (not a guest network).
- **Local control is on** in the bulb's phone app (WiZ: Security, turn off "only allow verified
  controls"; Govee: LAN Control on).
- On a Mac, **Local Network** access is allowed: System Settings > Privacy & Security > Local
  Network.
- Some routers block devices from seeing each other ("AP isolation" or a guest network). Try
  **Add by IP** on the Bulbs tab with the bulb's address from its phone app.

## The bulb says it isn't answering

Its address may have changed after a router restart. On the **Bulbs** tab, press **Find bulbs
on the network**. If your bulb has moved, you'll see **Update address**. In your router, giving
the bulb a fixed address (a "DHCP reservation") stops it from moving again.

## The light doesn't flash on a score

- The Status page shows **Dry-run: effects are logged, not sent to bulbs.** In the settings
  file, set `dispatch_enabled = true` and restart the app.
- The team has no bulb ticked: open **Teams**, tick the bulb and **Save**.
- Another computer is running the app and flashing the same bulb, or this one is the spare
  (see *Good to know* on the [setup page](first-setup.md)).
- Test it: press **Test** next to the team on the Teams tab.

## The light is too early or too late

That's the delay. See **[line it up with your TV](game-day.md)**. Practice mode measures it
for you during a game.

## Sending a report to the person who set this up

1. Open the **Diagnostics** tab.
2. Press **Copy for text message** and paste it into a text. It has no passwords in it.
3. Say what you expected and what happened.
