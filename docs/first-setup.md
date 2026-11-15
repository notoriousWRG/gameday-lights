# Set it up

You'll do this once, in the browser, on the computer where you installed Gameday Lights. Open
<http://127.0.0.1:8787/>. The **Status** page shows a **Finish setting up** list at the top.
It checks items off as you go, and anything that's wrong shows up there too.

## 1. Add your bulb

1. Open the **Bulbs** tab.
2. Press **Find bulbs on the network**. After about 5 seconds, any WiZ or Govee bulbs that
   answered are listed.
3. Press **Add** next to yours and give it a name you'll recognize, like "Living room".
4. Press **Save**.
5. Press **Ping & test** on the bulb. It should flash and go back to how it was.

!!! tip "Bulb not listed?"
    Check that it's on, on the same Wi-Fi as this computer, and that local control is turned
    on in its phone app (see the install page). You can also press **Add by IP** and type the
    bulb's address, which the bulb's phone app shows in its device info. If it still won't show
    up, see [When something is wrong](troubleshooting.md).

## 2. Follow a team

1. Open the **Teams** tab.
2. Under **Follow a team**, pick the league (NFL or NHL) and search for your team by name or
   abbreviation, like "Packers" or "GB".
3. Press **Follow**. The team's colors are filled in for you. You can change them.
4. Under the team, tick the **bulb** it should light.
5. Press **Save**. The team's schedule loads within a few seconds, and the **Schedule** card on
   the Status page shows its games.

## 3. Press Test

On the **Teams** tab, press **Test** next to your team. The bulb flashes the team's real score
effect in its colors, then goes back to how it was. This is what a touchdown or goal will
look like.

To change how it looks (how long, which pattern for a strip, a different look for each team),
use the **Effects** tab. Each change has its own **Test** button.

!!! note "Lights are off in a test copy"
    If the Status page says **Dry-run: effects are logged, not sent to bulbs**, this copy of
    the app is set to practice without flashing anything. Change `dispatch_enabled` to `true`
    in the settings file (see *Where your settings are* below) and restart the app.

## 4. Line it up with your TV

Streaming runs behind live TV, so the light waits a little after a score before it flashes. How
long depends on how you watch. Do this once, before a game, so the light doesn't spoil a play:
**[line it up with your TV](game-day.md)**.

## Good to know

**Only one computer should drive a bulb.** If you install on a second computer (say, to try
it), set `dispatch_enabled = false` in that computer's settings file, or both will flash the
same bulb. That setting lives in the file and not in the web page on purpose, so a spare
computer can never flash your lights by accident.

**Where your settings are.** On a Mac, in
`~/Library/Application Support/gameday-lights/config.toml`. To open it:

```bash
open -e "$HOME/Library/Application Support/gameday-lights/config.toml"
```

After editing it, restart the app. Do this between games. A score that happens while the app
restarts is skipped.

```bash
launchctl kickstart -k gui/$(id -u)/com.gameday-lights
```

**Using it from your phone.** By default the page only opens on the computer itself. To open
it from a phone on your home Wi-Fi, set `host` under `[web]` in the settings file to that
computer's address on your network (System Settings > Wi-Fi > Details shows it, something like
`192.168.1.20`), restart, then open `http://192.168.1.20:8787/` on the phone. There's no
password, so only do this on your home network.
